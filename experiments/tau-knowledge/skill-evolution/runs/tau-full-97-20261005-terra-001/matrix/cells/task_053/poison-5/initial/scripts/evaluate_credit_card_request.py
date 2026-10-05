#!/usr/bin/env python3
"""Pure policy calculator for Rho-Bank dispute and CLI workflows.
Reads one JSON object on stdin and writes one JSON object on stdout.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

TIERS = {
    "entry": {"max_fraction": Decimal("0.25"), "age_days": 120, "cooldown_days": 120,
              "utilization_lt": Decimal("70"), "payment_months": 6, "provisional_cap": Decimal("2500")},
    "mid": {"max_fraction": Decimal("0.50"), "age_days": 90, "cooldown_days": 90,
            "utilization_lt": Decimal("80"), "payment_months": 3, "provisional_cap": Decimal("5000")},
    "premium": {"max_fraction": Decimal("0.50"), "age_days": 60, "cooldown_days": 60,
                "utilization_lt": Decimal("90"), "payment_months": 3, "provisional_cap": Decimal("10000")},
}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: %s" % value)


def money(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s must be numeric" % name)
    if not result.is_finite():
        raise ValueError("%s must be finite" % name)
    return result


def failure(reason, detail):
    return {"reason": reason, "detail": detail}


def tier_for(value):
    if value not in TIERS:
        raise ValueError("tier must be one of entry, mid, premium")
    return TIERS[value]


def evaluate_dispute(data, today):
    required = ("reason", "amount", "purchase_date", "contacted_merchant", "tier")
    missing = [key for key in required if key not in data]
    if missing:
        return {"eligible_for_provisional_credit": None,
                "failures": [failure("insufficient_data", "missing: " + ", ".join(missing))]}
    policy = tier_for(data["tier"])
    reason = data["reason"]
    amount = money(data["amount"], "dispute.amount")
    purchase = parse_date(data["purchase_date"])
    failures = []
    age_days = data.get("account_age_days")
    if age_days is None and data.get("account_opened_on"):
        age_days = (today - parse_date(data["account_opened_on"])).days
    if age_days is None:
        failures.append(failure("insufficient_data", "account age is required"))
    elif int(age_days) < 60:
        failures.append(failure("account_age", "account must be open at least 60 days"))
    allowed = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    if reason not in allowed:
        failures.append(failure("reason", "reason is not eligible for provisional credit"))
    purchase_age = (today - purchase).days
    if reason == "goods_services_not_received" and purchase_age <= 30:
        failures.append(failure("purchase_age", "goods/services not received must be more than 30 days old"))
    if amount < Decimal("25") or amount > policy["provisional_cap"]:
        failures.append(failure("amount", "amount must be from 25 through tier provisional cap"))
    dates = []
    for item in data.get("prior_dispute_dates", []):
        dates.append(parse_date(item))
    cutoff = today - timedelta(days=365)
    count = sum(1 for item in dates if cutoff <= item <= today)
    if count > 2:
        failures.append(failure("prior_disputes", "more than two disputes in prior 12 months"))
    if reason != "unauthorized_fraudulent_charge" and data["contacted_merchant"] is not True:
        failures.append(failure("merchant_contact", "non-fraud dispute requires merchant contact"))
    return {
        "eligible_for_provisional_credit": not failures,
        "prior_disputes_in_12_months": count,
        "purchase_age_days": purchase_age,
        "tier_provisional_cap": str(policy["provisional_cap"]),
        "failures": failures,
    }


def latest_history(history):
    dated = []
    for item in history:
        if not isinstance(item, dict) or "submitted_at" not in item:
            raise ValueError("each CLI history record requires submitted_at")
        dated.append((parse_date(item["submitted_at"]), item))
    return max(dated, key=lambda pair: pair[0]) if dated else None


def evaluate_cli(data, today):
    required_account = ("tier", "opened_on", "current_limit", "current_balance", "past_due_amount", "is_current")
    if any(key not in data.get("account", {}) for key in required_account):
        return {"decision": "insufficient_data", "failures": [failure("insufficient_data", "incomplete account data")]}
    if "requested_increase_amount" not in data:
        return {"decision": "insufficient_data", "failures": [failure("insufficient_data", "requested_increase_amount is required")]}
    account = data["account"]
    policy = tier_for(account["tier"])
    current_limit = money(account["current_limit"], "account.current_limit")
    balance = money(account["current_balance"], "account.current_balance")
    past_due = money(account["past_due_amount"], "account.past_due_amount")
    requested = money(data["requested_increase_amount"], "requested_increase_amount")
    maximum = current_limit * policy["max_fraction"]
    precheck_failures = []
    if requested <= 0 or requested != requested.to_integral_value():
        precheck_failures.append(failure("other", "increase must be a positive whole-dollar amount"))
    if requested > maximum:
        precheck_failures.append(failure("requested_amount_exceeds_limit", "increase exceeds tier maximum"))
    base = {"maximum_increase": str(maximum), "requested_increase": str(requested),
            "new_credit_limit": str(current_limit + requested)}
    if precheck_failures:
        base.update({"decision": "precheck_rejected", "failures": precheck_failures,
                     "denial_reason": "requested_amount_exceeds_limit" if requested > maximum else "other"})
        return base
    if data.get("submitted") is not True:
        base.update({"decision": "submit_required", "failures": []})
        return base
    failures = []
    opened = parse_date(account["opened_on"])
    account_age = (today - opened).days
    if account_age < policy["age_days"]:
        failures.append(failure("insufficient_account_age", "account age is below tier minimum"))
    latest = latest_history(data.get("history", []))
    cooldown_until = None
    if latest and str(latest[1].get("status", "")).lower() == "approved":
        cooldown_until = latest[0] + timedelta(days=policy["cooldown_days"])
        if today < cooldown_until:
            failures.append(failure("cooldown_period_active", "cooldown has not fully elapsed"))
    if int(data.get("active_disputes", 0)) > 0:
        failures.append(failure("pending_disputes", "one or more disputes are active"))
    nonfinal_orders = [o for o in data.get("replacement_orders", [])
                       if not isinstance(o, dict) or str(o.get("status", "")).lower() not in FINAL_REPLACEMENT_STATUSES]
    if nonfinal_orders:
        failures.append(failure("pending_replacement_card", "replacement order is not final"))
    if past_due > 0 or account["is_current"] is not True:
        failures.append(failure("past_due_balance", "account is not current or has past-due amount"))
    if current_limit <= 0:
        failures.append(failure("other", "current limit must be positive"))
        utilization = None
    else:
        utilization = balance * Decimal("100") / current_limit
        if utilization >= policy["utilization_lt"]:
            failures.append(failure("high_utilization", "utilization is at or above tier threshold"))
    if int(data.get("consecutive_on_time_months", -1)) < policy["payment_months"]:
        failures.append(failure("insufficient_payment_history", "not enough consecutive on-time payments"))
    precedence = ["insufficient_account_age", "cooldown_period_active", "pending_disputes",
                  "pending_replacement_card", "past_due_balance", "high_utilization",
                  "insufficient_payment_history", "other"]
    reason = next((candidate for candidate in precedence if any(x["reason"] == candidate for x in failures)), None)
    base.update({
        "decision": "deny" if failures else "approve",
        "denial_reason": reason,
        "account_age_days": account_age,
        "utilization_percent": None if utilization is None else str(utilization),
        "cooldown_ends_on": None if cooldown_until is None else cooldown_until.isoformat(),
        "failures": failures,
    })
    return base


def main():
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        today = parse_date(raw["now"])
        output = {}
        if "dispute" in raw:
            output["dispute"] = evaluate_dispute(raw["dispute"], today)
        if "cli" in raw:
            cli_data = dict(raw["cli"])
            cli_data["account"] = raw.get("account", {})
            output["cli"] = evaluate_cli(cli_data, today)
        if not output:
            raise ValueError("provide dispute and/or cli")
        print(json.dumps(output, sort_keys=True))
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
