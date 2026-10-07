#!/usr/bin/env python3
"""Pure CLI eligibility calculator. Reads one JSON object from stdin; writes JSON."""
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
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result

def main(payload):
    tier = payload.get("tier")
    if tier not in RULES:
        raise ValueError("tier must be Entry-tier, Mid-tier, or Premium-tier")
    rule = RULES[tier]
    limit = money(payload.get("current_limit"), "current_limit")
    balance = money(payload.get("current_balance"), "current_balance")
    requested = money(payload.get("requested_increase_amount"), "requested_increase_amount")
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
        cooldown_days = None
        cooldown_pass = True
    else:
        submitted = parse_date(last_approved, "last_approved_request_date")
        if submitted > as_of:
            raise ValueError("last_approved_request_date cannot be after as_of")
        cooldown_days = (as_of - submitted).days
        cooldown_pass = cooldown_days >= rule["cooldown"]

    checks = {
        "requested_amount_within_limit": requested > 0 and requested <= max_increase,
        "minimum_account_age": account_age_days >= rule["age"],
        "cooldown_elapsed": cooldown_pass,
        "account_current_and_no_past_due": bool(payload.get("account_current")) and money(payload.get("past_due_amount"), "past_due_amount") <= 0,
        "no_active_dispute": not bool(payload.get("has_active_dispute")),
        "no_pending_replacement": not bool(payload.get("has_pending_replacement")),
        "utilization_below_threshold": utilization < rule["utilization"],
        "sufficient_payment_history": int(payload.get("consecutive_on_time_months", -1)) >= rule["payments"],
    }
    blockers = [name for name, passed in checks.items() if not passed]
    denial_map = {
        "minimum_account_age": "insufficient_account_age",
        "cooldown_elapsed": "cooldown_period_active",
        "no_active_dispute": "pending_disputes",
        "no_pending_replacement": "pending_replacement_card",
        "account_current_and_no_past_due": "past_due_balance",
        "utilization_below_threshold": "high_utilization",
        "sufficient_payment_history": "insufficient_payment_history",
        "requested_amount_within_limit": "requested_amount_exceeds_limit",
    }
    return {
        "tier": tier,
        "account_age_days": account_age_days,
        "cooldown_days_since_last_approved_request": cooldown_days,
        "required": {"minimum_age_days": rule["age"], "cooldown_days": rule["cooldown"], "max_utilization_percent_exclusive": float(rule["utilization"]), "on_time_months": rule["payments"]},
        "current_utilization_percent": float(utilization),
        "maximum_increase_amount": float(max_increase),
        "new_credit_limit_if_approved": float(limit + requested),
        "checks": checks,
        "blockers": blockers,
        "recommended_decision": "approve" if not blockers else "deny",
        "recommended_denial_reason": None if not blockers else denial_map[blockers[0]],
    }

try:
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict):
        raise ValueError("input must be a JSON object")
    print(json.dumps(main(raw), sort_keys=True))
except Exception as exc:
    print(json.dumps({"error": str(exc)}))
    sys.exit(2)
