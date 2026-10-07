#!/usr/bin/env python3
"""Evaluate normalized CLI policy facts. Reads one JSON object from stdin, emits JSON."""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "months": 6, "maximum_fraction": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "months": 3, "maximum_fraction": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "months": 3, "maximum_fraction": Decimal("0.50")},
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError("dates must begin with YYYY-MM-DD") from exc


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def main(data):
    required = ["tier", "as_of", "opened_on", "current_limit", "current_balance",
                "requested_increase", "approved_request_dates", "active_dispute",
                "pending_replacement", "past_due", "consecutive_on_time_months"]
    missing = [key for key in required if key not in data]
    if missing:
        return {"outcome": "manual_review_required", "error": "missing required fields", "missing": missing}

    tier = str(data["tier"]).lower().replace("-tier", "").strip()
    if tier not in POLICY:
        return {"outcome": "manual_review_required", "error": "unsupported tier"}
    p = POLICY[tier]
    try:
        today = parse_date(data["as_of"])
        opened = parse_date(data["opened_on"])
        limit = money(data["current_limit"], "current_limit")
        balance = money(data["current_balance"], "current_balance")
        increase = money(data["requested_increase"], "requested_increase")
        approved = [parse_date(x) for x in data["approved_request_dates"]]
        months = int(data["consecutive_on_time_months"])
    except (ValueError, TypeError) as exc:
        return {"outcome": "manual_review_required", "error": str(exc)}

    if limit <= 0 or balance < 0 or increase <= 0 or opened > today or months < 0:
        return {"outcome": "manual_review_required", "error": "invalid account facts"}

    maximum = limit * p["maximum_fraction"]
    proposed = limit + increase
    # Amount precheck happens before submission and intentionally has no denial action.
    if increase > maximum:
        return {
            "outcome": "request_amount_invalid",
            "maximum_increase": str(maximum),
            "proposed_new_limit": str(proposed),
            "message": "Do not submit; obtain confirmation of an amount at or below the maximum.",
        }

    age_days = (today - opened).days
    utilization = (balance / limit) * Decimal("100")
    latest_approved = max(approved) if approved else None
    cooldown_days = (today - latest_approved).days if latest_approved else None
    checks = {
        "account_age": age_days >= p["age"],
        "cooldown": latest_approved is None or cooldown_days >= p["cooldown"],
        "no_active_dispute": data["active_dispute"] is False,
        "no_pending_replacement": data["pending_replacement"] is False,
        "good_standing": data["past_due"] is False,
        "utilization": utilization < p["utilization"],
        "payment_history": months >= p["months"],
    }
    reason_map = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("no_active_dispute", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    denial = next((reason for check, reason in reason_map if not checks[check]), None)
    return {
        "outcome": "eligible" if denial is None else "denial_reason",
        "denial_reason": denial,
        "maximum_increase": str(maximum),
        "proposed_new_limit": str(proposed),
        "account_age_days": age_days,
        "utilization_percent": str(utilization),
        "latest_approved_request_date": latest_approved.isoformat() if latest_approved else None,
        "cooldown_elapsed_days": cooldown_days,
        "checks": checks,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"outcome": "manual_review_required", "error": str(exc)}, sort_keys=True))
