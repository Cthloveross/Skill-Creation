#!/usr/bin/env python3
"""Pure CLI eligibility calculator: one JSON object on stdin, one JSON object on stdout."""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

RULES = {
    "Entry-tier": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payments": 6, "maximum": Decimal("0.25")},
    "Mid-tier": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payments": 3, "maximum": Decimal("0.50")},
    "Premium-tier": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payments": 3, "maximum": Decimal("0.50")},
}

def parse_date(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty ISO date or timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO-8601") from exc

def money(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result

def boolean(value, field):
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a JSON boolean")
    return value

def nonnegative_integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value

def as_number(value):
    """JSON-friendly decimal output without avoidable binary conversion in decisions."""
    return float(value)

def main(payload):
    tier = payload.get("tier")
    if tier not in RULES:
        raise ValueError("tier must be Entry-tier, Mid-tier, or Premium-tier")
    rule = RULES[tier]
    limit = money(payload.get("current_limit"), "current_limit")
    balance = money(payload.get("current_balance"), "current_balance")
    requested = money(payload.get("requested_increase_amount"), "requested_increase_amount")
    past_due = money(payload.get("past_due_amount"), "past_due_amount")
    if limit <= 0:
        raise ValueError("current_limit must be greater than zero")

    as_of = parse_date(payload.get("as_of"), "as_of")
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of")
    account_age_days = (as_of - opened).days
    max_increase = limit * rule["maximum"]
    utilization = balance / limit * Decimal("100")

    last_approved = payload.get("last_approved_request_date")
    if last_approved is None:
        cooldown_days, cooldown_pass = None, True
    else:
        submitted = parse_date(last_approved, "last_approved_request_date")
        if submitted > as_of:
            raise ValueError("last_approved_request_date cannot be after as_of")
        cooldown_days = (as_of - submitted).days
        cooldown_pass = cooldown_days >= rule["cooldown"]

    whole_dollar = requested == requested.to_integral_value()
    amount_within_limit = requested > 0 and whole_dollar and requested <= max_increase
    checks = {
        "minimum_account_age": account_age_days >= rule["age"],
        "cooldown_elapsed": cooldown_pass,
        "account_current_and_no_past_due": boolean(payload.get("account_current"), "account_current") and past_due <= 0,
        "no_active_dispute": not boolean(payload.get("has_active_dispute"), "has_active_dispute"),
        "no_pending_replacement": not boolean(payload.get("has_pending_replacement"), "has_pending_replacement"),
        "utilization_below_threshold": utilization < rule["utilization"],
        "sufficient_payment_history": nonnegative_integer(payload.get("consecutive_on_time_months"), "consecutive_on_time_months") >= rule["payments"],
    }
    blockers = [name for name, passed in checks.items() if not passed]
    denial_map = {
        "minimum_account_age": "insufficient_account_age",
        "cooldown_elapsed": "cooldown_period_active",
        "account_current_and_no_past_due": "past_due_balance",
        "no_active_dispute": "pending_disputes",
        "no_pending_replacement": "pending_replacement_card",
        "utilization_below_threshold": "high_utilization",
        "sufficient_payment_history": "insufficient_payment_history",
    }
    return {
        "tier": tier,
        "account_age_days": account_age_days,
        "cooldown_days_since_last_approved_request": cooldown_days,
        "required": {"minimum_age_days": rule["age"], "cooldown_days": rule["cooldown"], "max_utilization_percent_exclusive": as_number(rule["utilization"]), "on_time_months": rule["payments"]},
        "current_utilization_percent": as_number(utilization),
        "maximum_increase_amount": as_number(max_increase),
        "requested_increase_is_whole_dollars": whole_dollar,
        "pre_submission_valid": amount_within_limit,
        "new_credit_limit_if_approved": as_number(limit + requested),
        "checks": checks,
        "blockers": blockers,
        "recommended_decision": ("do_not_submit" if not amount_within_limit else ("approve" if not blockers else "deny")),
        "recommended_denial_reason": (None if not amount_within_limit or not blockers else denial_map[blockers[0]]),
    }

try:
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict):
        raise ValueError("input must be a JSON object")
    print(json.dumps(main(raw), sort_keys=True))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    sys.exit(2)
