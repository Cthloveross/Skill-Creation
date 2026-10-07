#!/usr/bin/env python3
"""Deterministically evaluate documented CLI thresholds; reads JSON stdin, writes JSON stdout."""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "months": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "months": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "months": 3, "max_fraction": Decimal("0.50")},
}
DENIAL_ORDER = [
    ("account_age_ok", "insufficient_account_age"),
    ("cooldown_ok", "cooldown_period_active"),
    ("disputes_ok", "pending_disputes"),
    ("replacement_ok", "pending_replacement_card"),
    ("standing_ok", "past_due_balance"),
    ("utilization_ok", "high_utilization"),
    ("payment_history_ok", "insufficient_payment_history"),
    ("requested_amount_ok", "requested_amount_exceeds_limit"),
]

def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc

def amount(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative finite amount")
    return result

def fmt(value):
    return format(value.quantize(Decimal("0.01")), "f")

def main(data):
    tier = data.get("tier")
    if tier not in POLICY:
        raise ValueError("tier must be entry, mid, or premium")
    policy = POLICY[tier]
    as_of = parse_date(data.get("as_of_date"), "as_of_date")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of_date")
    limit = amount(data.get("current_credit_limit"), "current_credit_limit")
    balance = amount(data.get("current_balance"), "current_balance")
    requested = amount(data.get("requested_increase"), "requested_increase")
    past_due = amount(data.get("past_due_amount"), "past_due_amount")
    if limit <= 0:
        raise ValueError("current_credit_limit must be greater than zero")
    if requested != requested.to_integral_value():
        raise ValueError("requested_increase must be an integer number of dollars")
    history = data.get("approved_request_dates")
    if not isinstance(history, list):
        raise ValueError("approved_request_dates must be a list")
    approved_dates = [parse_date(x, "approved_request_dates entry") for x in history]
    if any(x > as_of for x in approved_dates):
        raise ValueError("approved_request_dates cannot be in the future")
    months = data.get("payment_months_on_time")
    if isinstance(months, bool) or not isinstance(months, int) or months < 0:
        raise ValueError("payment_months_on_time must be a nonnegative integer")
    for key in ("has_active_dispute", "has_pending_replacement"):
        if not isinstance(data.get(key), bool):
            raise ValueError(f"{key} must be boolean")

    maximum = limit * policy["max_fraction"]
    utilization = balance / limit * Decimal("100")
    latest = max(approved_dates) if approved_dates else None
    cooldown_eligible = latest + timedelta(days=policy["cooldown"]) if latest else None
    checks = {
        "account_age_ok": (as_of - opened).days >= policy["age"],
        "cooldown_ok": cooldown_eligible is None or as_of >= cooldown_eligible,
        "disputes_ok": not data["has_active_dispute"],
        "replacement_ok": not data["has_pending_replacement"],
        "standing_ok": past_due == 0,
        "utilization_ok": utilization < policy["utilization"],
        "payment_history_ok": months >= policy["months"],
        "requested_amount_ok": requested <= maximum,
    }
    denial_reason = next((reason for check, reason in DENIAL_ORDER if not checks[check]), None)
    return {
        "ok": True,
        "tier": tier,
        "account_age_days": (as_of - opened).days,
        "minimum_account_age_days": policy["age"],
        "cooldown_days": policy["cooldown"],
        "cooldown_eligible_date": cooldown_eligible.isoformat() if cooldown_eligible else None,
        "max_utilization_percent_exclusive": str(policy["utilization"]),
        "utilization_percent": str(utilization),
        "required_on_time_months": policy["months"],
        "maximum_increase": fmt(maximum),
        "new_credit_limit": fmt(limit + requested),
        "checks": checks,
        "decision": "approve" if denial_reason is None else "deny",
        "denial_reason": denial_reason,
    }

if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
