#!/usr/bin/env python3
"""Deterministic eligibility calculator for a normalized credit-card case.
Reads JSON from stdin and writes JSON to stdout.  No network or tool calls.
"""
import json
import re
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CLI_RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "increase_pct": Decimal("25"), "months": 6},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "increase_pct": Decimal("50"), "months": 3},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "increase_pct": Decimal("50"), "months": 3},
}
PROVISIONAL_CAPS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"),
    "elite": Decimal("15000"), "invitation": Decimal("25000"),
}
PROVISIONAL_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}


def tier_name(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower().replace("_", "-")
    aliases = {
        "entry-tier": "entry", "mid-tier": "mid", "premium-tier": "premium",
        "elite-tier": "elite", "invitation-tier": "invitation",
    }
    return aliases.get(value, value)


def parse_date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    raw = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("invalid date: " + raw) from exc


def money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing monetary value")
    try:
        cleaned = re.sub(r"[$,\s]", "", str(value))
        return Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc


def fmt_amount(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def bool_value(obj, key, errors):
    value = obj.get(key)
    if not isinstance(value, bool):
        errors.append(key + " must be boolean")
        return None
    return value


def dates_within(values, today, errors, label):
    if not isinstance(values, list):
        errors.append(label + " must be an array")
        return []
    cutoff = today.replace(year=today.year - 1)
    parsed = []
    for value in values:
        try:
            item = parse_date(value)
        except ValueError:
            errors.append(label + " contains an invalid date")
            continue
        if item > today:
            errors.append(label + " contains a future date")
        elif item >= cutoff:
            parsed.append(item)
    return parsed


def check(name, passed, detail, unavailable=False):
    return {"name": name, "passed": passed, "unavailable": unavailable, "detail": detail}


def main(payload):
    errors = []
    try:
        today = parse_date(payload.get("now"))
    except ValueError as exc:
        return {"input_errors": [str(exc)]}
    account = payload.get("account")
    if not isinstance(account, dict):
        return {"input_errors": ["account must be an object"]}
    try:
        opened = parse_date(account.get("opened_on"))
        balance = money(account.get("current_balance"))
        limit = money(account.get("credit_limit"))
        past_due = money(account.get("past_due_amount"))
        if limit <= 0:
            errors.append("credit_limit must be positive")
        if opened > today:
            errors.append("opened_on cannot be in the future")
    except ValueError as exc:
        errors.append(str(exc))
        opened, balance, limit, past_due = None, None, None, None
    result = {"input_errors": errors, "as_of": today.isoformat()}
    if errors:
        return result

    account_age = (today - opened).days
    result["account"] = {
        "age_days": account_age,
        "utilization_percent": fmt_amount((balance / limit) * Decimal("100")),
    }

    dispute = payload.get("dispute")
    if dispute is not None:
        result["dispute"] = evaluate_dispute(dispute, today, account_age)
    cli = payload.get("cli")
    if cli is not None:
        result["cli"] = evaluate_cli(cli, today, account_age, balance, limit, past_due, account.get("status"))
    return result


def evaluate_dispute(dispute, today, account_age):
    errors, checks = [], []
    if not isinstance(dispute, dict):
        return {"input_errors": ["dispute must be an object"]}
    tier = tier_name(dispute.get("tier"))
    if tier not in PROVISIONAL_CAPS:
        errors.append("unsupported provisional-credit tier")
    reason = dispute.get("reason")
    try:
        amount = money(dispute.get("amount"))
        purchase_date = parse_date(dispute.get("purchase_date"))
    except ValueError as exc:
        errors.append(str(exc))
        amount, purchase_date = None, None
    contacted = bool_value(dispute, "contacted_merchant", errors)
    history = dates_within(dispute.get("prior_dispute_dates", []), today, errors, "prior_dispute_dates")
    if errors:
        return {"input_errors": errors, "eligible_for_provisional_credit": False}
    purchase_age = (today - purchase_date).days
    cap = PROVISIONAL_CAPS[tier]
    checks.append(check("account_age", account_age >= 60, "account age is %d days; minimum is 60" % account_age))
    allowed_reason = reason in PROVISIONAL_REASONS
    checks.append(check("eligible_reason", allowed_reason, "reason must be one of the provisional-credit eligible categories"))
    delivery_ok = reason != "goods_services_not_received" or purchase_age > 30
    checks.append(check("delivery_wait", delivery_ok, "purchase age is %d days; goods-not-received requires more than 30 days" % purchase_age))
    amount_ok = amount >= Decimal("25") and amount <= cap
    checks.append(check("amount", amount_ok, "amount %s; permitted range is 25.00 through %s" % (fmt_amount(amount), fmt_amount(cap))))
    history_ok = len(history) <= 2
    checks.append(check("prior_disputes", history_ok, "%d disputes filed in the preceding 12 months; maximum is 2" % len(history)))
    merchant_ok = reason == "unauthorized_fraudulent_charge" or contacted is True
    checks.append(check("merchant_contact", merchant_ok, "merchant contact is required for non-fraud disputes"))
    return {
        "input_errors": [], "eligible_for_provisional_credit": all(item["passed"] for item in checks),
        "purchase_age_days": purchase_age, "prior_disputes_12_months": len(history), "checks": checks,
    }


def evaluate_cli(cli, today, account_age, balance, limit, past_due, status):
    errors, checks = [], []
    if not isinstance(cli, dict):
        return {"input_errors": ["cli must be an object"]}
    tier = tier_name(cli.get("tier"))
    if tier not in CLI_RULES:
        return {"input_errors": ["unsupported CLI tier"], "should_submit": False}
    rule = CLI_RULES[tier]
    try:
        requested = money(cli.get("requested_increase_amount"))
    except ValueError as exc:
        return {"input_errors": [str(exc)], "should_submit": False}
    maximum = limit * rule["increase_pct"] / Decimal("100")
    amount_valid = requested > 0 and requested <= maximum
    base = {
        "input_errors": [], "tier": tier, "requested_increase_amount": fmt_amount(requested),
        "maximum_increase_amount": fmt_amount(maximum), "should_submit": amount_valid,
        "amount_within_pre_submit_cap": amount_valid,
    }
    if not amount_valid:
        base.update({"can_decide": False, "approved": False, "denial_reason": None,
                     "message": "Do not submit a CLI request; obtain a confirmed positive amount at or below the maximum."})
        return base

    approved_dates = dates_within(cli.get("prior_approved_request_dates", []), today, errors, "prior_approved_request_dates")
    active_disputes = bool_value(cli, "has_active_disputes", errors)
    pending_replacement = bool_value(cli, "has_pending_replacement", errors)
    on_time_months = cli.get("consecutive_on_time_months")
    if isinstance(on_time_months, bool) or not isinstance(on_time_months, int) or on_time_months < 0:
        errors.append("consecutive_on_time_months must be a nonnegative integer")
    if errors:
        base.update({"input_errors": errors, "can_decide": False, "approved": False, "denial_reason": None})
        return base

    checks.append(check("account_age", account_age >= rule["age"], "account age is %d days; minimum is %d" % (account_age, rule["age"])))
    latest = max(approved_dates) if approved_dates else None
    cooldown_end = latest + timedelta(days=rule["cooldown"]) if latest else None
    cooldown_ok = cooldown_end is None or today >= cooldown_end
    checks.append(check("cooldown", cooldown_ok, "no previous approved request" if latest is None else "cooldown ends on " + cooldown_end.isoformat()))
    checks.append(check("pending_disputes", not active_disputes, "active dispute status supplied by executor"))
    checks.append(check("pending_replacement", not pending_replacement, "replacement-order status supplied by executor"))
    standing = past_due <= 0 and (status is None or str(status).upper() == "ACTIVE")
    checks.append(check("good_standing", standing, "past due amount is " + fmt_amount(past_due)))
    utilization = (balance / limit) * Decimal("100")
    checks.append(check("utilization", utilization < rule["utilization"], "utilization is %s%%; must be below %s%%" % (fmt_amount(utilization), fmt_amount(rule["utilization"]))))
    checks.append(check("payment_history", on_time_months >= rule["months"], "%d consecutive on-time months; requires %d" % (on_time_months, rule["months"])))
    failure_reason = {
        "account_age": "insufficient_account_age", "cooldown": "cooldown_period_active",
        "pending_disputes": "pending_disputes", "pending_replacement": "pending_replacement_card",
        "good_standing": "past_due_balance", "utilization": "high_utilization",
        "payment_history": "insufficient_payment_history",
    }
    failed = next((item for item in checks if not item["passed"]), None)
    base.update({
        "can_decide": True, "approved": failed is None,
        "denial_reason": None if failed is None else failure_reason[failed["name"]],
        "new_credit_limit_if_approved": fmt_amount(limit + requested), "checks": checks,
    })
    if cooldown_end is not None:
        base["cooldown_eligible_on"] = cooldown_end.isoformat()
    return base


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level JSON must be an object")
        json.dump(main(incoming), sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"input_errors": [str(exc)]}, sys.stdout)
        sys.stdout.write("\n")
