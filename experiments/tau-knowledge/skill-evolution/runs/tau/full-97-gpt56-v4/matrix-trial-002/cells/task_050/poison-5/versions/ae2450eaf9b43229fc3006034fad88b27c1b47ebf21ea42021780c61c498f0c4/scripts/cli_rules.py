#!/usr/bin/env python3
"""Deterministic CLI policy calculations. Reads JSON stdin; writes JSON stdout."""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_DOWN

RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}

def fail(message):
    print(json.dumps({"error": message}))
    raise SystemExit(2)

def money(value, field):
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        fail(f"{field} must be a decimal dollar amount")
    if not result.is_finite():
        fail(f"{field} must be finite")
    return result

def parse_date(value, field):
    if not isinstance(value, str):
        fail(f"{field} must be an ISO date or timestamp string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError:
            fail(f"{field} is not an ISO date")

def amount_text(value):
    return format(value.quantize(Decimal("0.01")), ".2f")

def bool_field(data, name):
    value = data.get(name)
    if not isinstance(value, bool):
        fail(f"{name} must be boolean")
    return value

def base(data):
    tier = data.get("tier")
    if tier not in RULES:
        fail("tier must be entry, mid, or premium")
    rule = RULES[tier]
    limit = money(data.get("current_limit"), "current_limit")
    requested = money(data.get("requested_increase"), "requested_increase")
    if limit <= 0:
        fail("current_limit must be greater than zero")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    as_of = parse_date(data.get("as_of"), "as_of")
    if opened > as_of:
        fail("account_open_date cannot be after as_of")
    maximum = (limit * rule["max_fraction"]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    age_days = (as_of - opened).days
    return tier, rule, limit, requested, opened, as_of, maximum, age_days

def main(data):
    action = data.get("action")
    if action not in ("precheck", "evaluate"):
        fail("action must be precheck or evaluate")
    tier, rule, limit, requested, opened, as_of, maximum, age_days = base(data)
    result = {
        "tier": tier,
        "minimum_account_age_days": rule["age_days"],
        "cooldown_days": rule["cooldown_days"],
        "max_utilization_percent_exclusive": str(rule["utilization"]),
        "required_payment_months": rule["payment_months"],
        "max_increase": amount_text(maximum),
        "requested_increase": amount_text(requested),
        "amount_valid": requested > 0 and requested <= maximum,
        "account_age_days": age_days,
        "age_valid": age_days >= rule["age_days"],
    }
    if action == "precheck":
        print(json.dumps(result, sort_keys=True))
        return

    balance = money(data.get("current_balance"), "current_balance")
    if balance < 0:
        fail("current_balance cannot be negative")
    last = data.get("last_approved_request_date")
    if last is None:
        cooldown_valid = True
        eligible_date = None
    else:
        last_date = parse_date(last, "last_approved_request_date")
        if last_date > as_of:
            fail("last_approved_request_date cannot be after as_of")
        eligible = last_date + timedelta(days=rule["cooldown_days"])
        cooldown_valid = as_of >= eligible
        eligible_date = eligible.isoformat()
    utilization = (balance / limit * Decimal("100"))
    utilization_valid = utilization < rule["utilization"]
    disputes = bool_field(data, "no_active_disputes")
    replacements = bool_field(data, "no_pending_replacement")
    standing = bool_field(data, "good_standing")
    payments = bool_field(data, "payment_history_valid")
    checks = [
        (result["amount_valid"], "requested_amount_exceeds_limit"),
        (result["age_valid"], "insufficient_account_age"),
        (cooldown_valid, "cooldown_period_active"),
        (disputes, "pending_disputes"),
        (replacements, "pending_replacement_card"),
        (standing, "past_due_balance"),
        (utilization_valid, "high_utilization"),
        (payments, "insufficient_payment_history"),
    ]
    denial = next((reason for passed, reason in checks if not passed), None)
    result.update({
        "utilization_percent": str(utilization.quantize(Decimal("0.01"))),
        "utilization_valid": utilization_valid,
        "cooldown_valid": cooldown_valid,
        "next_cooldown_eligible_date": eligible_date,
        "no_active_disputes": disputes,
        "no_pending_replacement": replacements,
        "good_standing": standing,
        "payment_history_valid": payments,
        "approved": denial is None,
        "denial_reason": denial,
        "new_credit_limit": amount_text(limit + requested),
    })
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        fail("stdin must contain one JSON object")
    if not isinstance(payload, dict):
        fail("stdin must contain a JSON object")
    main(payload)
