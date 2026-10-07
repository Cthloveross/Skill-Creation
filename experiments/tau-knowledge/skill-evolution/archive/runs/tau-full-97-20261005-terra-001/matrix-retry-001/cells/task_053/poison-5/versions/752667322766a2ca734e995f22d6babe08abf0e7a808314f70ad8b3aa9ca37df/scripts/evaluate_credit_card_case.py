#!/usr/bin/env python3
"""Evaluate normalized credit-card dispute and CLI criteria without bank side effects.

Reads one JSON object from stdin and emits one JSON assessment to stdout.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CLI_RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "increase_pct": Decimal("25"), "months": 6},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "increase_pct": Decimal("50"), "months": 3},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "increase_pct": Decimal("50"), "months": 3},
}
CAPS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"),
    "elite": Decimal("15000"), "invitation": Decimal("25000"),
}
PROVISIONAL_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    raw = value.strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], pattern).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("invalid date: " + raw) from exc


def parse_money(value):
    if value is None or isinstance(value, bool):
        raise ValueError("missing monetary value")
    try:
        return Decimal(re.sub(r"[$,\s]", "", str(value)))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc


def display_money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def normalized_tier(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower().replace("_", "-")
    return {
        "entry-tier": "entry", "mid-tier": "mid", "premium-tier": "premium",
        "elite-tier": "elite", "invitation-tier": "invitation",
    }.get(value, value)


def check(name, passed, detail):
    return {"name": name, "passed": bool(passed), "unavailable": False, "detail": detail}


def prior_dates(values, today, field, errors):
    if not isinstance(values, list):
        errors.append(field + " must be an array")
        return []
    try:
        cutoff = today.replace(year=today.year - 1)
    except ValueError:  # February 29
        cutoff = today - timedelta(days=365)
    result = []
    for value in values:
        try:
            item = parse_date(value)
        except ValueError:
            errors.append(field + " contains an invalid date")
            continue
        if item > today:
            errors.append(field + " contains a future date")
        elif item >= cutoff:
            result.append(item)
    return result


def required_bool(obj, field, errors):
    value = obj.get(field)
    if not isinstance(value, bool):
        errors.append(field + " must be boolean")
        return False
    return value


def evaluate_dispute(data, today, age_days):
    if not isinstance(data, dict):
        return {"input_errors": ["dispute must be an object"]}
    errors = []
    tier = normalized_tier(data.get("tier"))
    if tier not in CAPS:
        errors.append("unsupported provisional-credit tier")
    try:
        amount = parse_money(data.get("amount"))
        purchased = parse_date(data.get("purchase_date"))
    except ValueError as exc:
        errors.append(str(exc))
        amount, purchased = Decimal("0"), today
    contacted = required_bool(data, "contacted_merchant", errors)
    history = prior_dates(data.get("prior_dispute_dates", []), today, "prior_dispute_dates", errors)
    if errors:
        return {"input_errors": errors, "eligible_for_provisional_credit": False}

    reason = data.get("reason")
    purchase_age = (today - purchased).days
    checks = [
        check("account_age", age_days >= 60, "account age is %d days; minimum is 60" % age_days),
        check("eligible_reason", reason in PROVISIONAL_REASONS, "reason must be a provisional-credit eligible category"),
        check("delivery_wait", reason != "goods_services_not_received" or purchase_age > 30,
              "purchase age is %d days; goods-not-received requires more than 30" % purchase_age),
        check("amount", amount >= Decimal("25") and amount <= CAPS[tier],
              "amount %s; permitted range is 25.00 through %s" % (display_money(amount), display_money(CAPS[tier]))),
        check("prior_disputes", len(history) <= 2,
              "%d disputes filed in the preceding 12 months; maximum is 2" % len(history)),
        check("merchant_contact", reason == "unauthorized_fraudulent_charge" or contacted,
              "merchant contact is required for a non-fraud dispute"),
    ]
    return {
        "input_errors": [],
        "purchase_age_days": purchase_age,
        "prior_disputes_12_months": len(history),
        "checks": checks,
        "eligible_for_provisional_credit": all(item["passed"] for item in checks),
    }


def evaluate_cli(data, today, age_days, balance, limit, past_due, status):
    if not isinstance(data, dict):
        return {"input_errors": ["cli must be an object"], "should_submit": False}
    tier = normalized_tier(data.get("tier"))
    if tier not in CLI_RULES:
        return {"input_errors": ["unsupported CLI tier"], "should_submit": False}
    try:
        requested = parse_money(data.get("requested_increase_amount"))
    except ValueError as exc:
        return {"input_errors": [str(exc)], "should_submit": False}

    rule = CLI_RULES[tier]
    maximum = limit * rule["increase_pct"] / Decimal("100")
    amount_ok = requested > 0 and requested <= maximum
    output = {
        "input_errors": [], "tier": tier,
        "requested_increase_amount": display_money(requested),
        "maximum_increase_amount": display_money(maximum),
        "amount_within_pre_submit_cap": amount_ok,
        "should_submit": amount_ok,
    }
    if not amount_ok:
        output.update({"can_decide": False, "approved": False, "denial_reason": None})
        return output

    errors = []
    approved_dates = prior_dates(data.get("prior_approved_request_dates", []), today,
                                 "prior_approved_request_dates", errors)
    active = required_bool(data, "has_active_disputes", errors)
    replacement = required_bool(data, "has_pending_replacement", errors)
    months = data.get("consecutive_on_time_months")
    if isinstance(months, bool) or not isinstance(months, int) or months < 0:
        errors.append("consecutive_on_time_months must be a nonnegative integer")
    if errors:
        output.update({"input_errors": errors, "can_decide": False, "approved": False, "denial_reason": None})
        return output

    latest = max(approved_dates) if approved_dates else None
    cooldown_end = latest + timedelta(days=rule["cooldown"]) if latest else None
    utilization = balance / limit * Decimal("100")
    standing = past_due <= 0 and (status is None or str(status).upper() == "ACTIVE")
    checks = [
        check("account_age", age_days >= rule["age"], "account age is %d days; minimum is %d" % (age_days, rule["age"])),
        check("cooldown", cooldown_end is None or today >= cooldown_end,
              "no prior approved request" if cooldown_end is None else "cooldown ends on " + cooldown_end.isoformat()),
        check("pending_disputes", not active, "active-dispute status supplied from post-submission history"),
        check("pending_replacement", not replacement, "replacement-order status supplied by executor"),
        check("good_standing", standing, "past due amount is " + display_money(past_due)),
        check("utilization", utilization < rule["utilization"],
              "utilization is %s%%; must be below %s%%" % (display_money(utilization), display_money(rule["utilization"]))),
        check("payment_history", months >= rule["months"],
              "%d consecutive on-time months; requires %d" % (months, rule["months"])),
    ]
    reason_map = {
        "account_age": "insufficient_account_age", "cooldown": "cooldown_period_active",
        "pending_disputes": "pending_disputes", "pending_replacement": "pending_replacement_card",
        "good_standing": "past_due_balance", "utilization": "high_utilization",
        "payment_history": "insufficient_payment_history",
    }
    failed = next((item for item in checks if not item["passed"]), None)
    output.update({
        "can_decide": True,
        "approved": failed is None,
        "denial_reason": None if failed is None else reason_map[failed["name"]],
        "new_credit_limit_if_approved": display_money(limit + requested),
        "checks": checks,
    })
    if cooldown_end is not None:
        output["cooldown_eligible_on"] = cooldown_end.isoformat()
    return output


def main(payload):
    if not isinstance(payload, dict):
        return {"input_errors": ["top-level JSON must be an object"]}
    try:
        today = parse_date(payload.get("now"))
    except ValueError as exc:
        return {"input_errors": [str(exc)]}
    account = payload.get("account")
    if not isinstance(account, dict):
        return {"input_errors": ["account must be an object"]}
    try:
        opened = parse_date(account.get("opened_on"))
        balance = parse_money(account.get("current_balance"))
        limit = parse_money(account.get("credit_limit"))
        past_due = parse_money(account.get("past_due_amount"))
        if opened > today:
            raise ValueError("opened_on cannot be in the future")
        if limit <= 0:
            raise ValueError("credit_limit must be positive")
    except ValueError as exc:
        return {"input_errors": [str(exc)]}

    age_days = (today - opened).days
    result = {
        "input_errors": [], "as_of": today.isoformat(),
        "account": {"age_days": age_days, "utilization_percent": display_money(balance / limit * Decimal("100"))},
    }
    if "dispute" in payload and payload["dispute"] is not None:
        result["dispute"] = evaluate_dispute(payload["dispute"], today, age_days)
    if "cli" in payload and payload["cli"] is not None:
        result["cli"] = evaluate_cli(payload["cli"], today, age_days, balance, limit, past_due, account.get("status"))
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        json.dump(main(payload), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"input_errors": [str(exc)]}, sys.stdout)
        sys.stdout.write("\n")
