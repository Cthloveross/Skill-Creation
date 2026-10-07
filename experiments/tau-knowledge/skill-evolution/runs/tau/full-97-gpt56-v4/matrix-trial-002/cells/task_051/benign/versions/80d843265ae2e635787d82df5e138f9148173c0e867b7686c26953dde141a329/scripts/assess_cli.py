#!/usr/bin/env python3
"""Deterministically assess normalized CLI eligibility data from stdin JSON."""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation

RULES = {
    "Entry-tier": {"days": 120, "utilization": Decimal("70"), "months": 6, "max_fraction": Decimal("0.25")},
    "Mid-tier": {"days": 90, "utilization": Decimal("80"), "months": 3, "max_fraction": Decimal("0.50")},
    "Premium-tier": {"days": 60, "utilization": Decimal("90"), "months": 3, "max_fraction": Decimal("0.50")},
}
REQUIRED = [
    "tier", "current_time", "date_of_account_open", "current_balance", "current_limit",
    "requested_increase", "last_cli_requests", "has_active_dispute", "has_pending_replacement",
    "account_current", "past_due_amount", "consecutive_on_time_months",
]


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    # The first ten characters support timestamps with a trailing timezone label.
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("use YYYY-MM-DD or MM/DD/YYYY")


def money(value, name):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name} must be numeric")
    if not number.is_finite():
        raise ValueError(f"{name} must be finite")
    return number


def main(data):
    missing = [key for key in REQUIRED if key not in data or data[key] is None]
    if missing:
        return {"action": "needs_information", "missing_fields": missing,
                "message": "Do not submit or decide until required normalized screening data is available."}
    if data["tier"] not in RULES:
        return {"action": "needs_information", "missing_fields": ["tier"],
                "message": "Tier must be Entry-tier, Mid-tier, or Premium-tier."}

    try:
        now = parse_date(data["current_time"])
        opened = parse_date(data["date_of_account_open"])
        balance = money(data["current_balance"], "current_balance")
        limit = money(data["current_limit"], "current_limit")
        increase = money(data["requested_increase"], "requested_increase")
        past_due = money(data["past_due_amount"], "past_due_amount")
    except ValueError as exc:
        return {"action": "needs_information", "missing_fields": [], "message": str(exc)}
    if limit <= 0 or balance < 0 or past_due < 0:
        return {"action": "needs_information", "missing_fields": [],
                "message": "Limit must be positive and balances cannot be negative."}
    if not isinstance(data["last_cli_requests"], list):
        return {"action": "needs_information", "missing_fields": ["last_cli_requests"],
                "message": "last_cli_requests must be a list."}

    rule = RULES[data["tier"]]
    age_days = (now - opened).days
    max_increase = limit * rule["max_fraction"]
    utilization = balance * Decimal("100") / limit
    approved_dates = []
    try:
        for request in data["last_cli_requests"]:
            if not isinstance(request, dict) or "status" not in request or "submitted_at" not in request:
                raise ValueError("Each CLI history entry needs status and submitted_at.")
            if str(request["status"]).strip().lower() == "approved":
                approved_dates.append(parse_date(request["submitted_at"]))
    except ValueError as exc:
        return {"action": "needs_information", "missing_fields": ["last_cli_requests"], "message": str(exc)}

    last_approved = max(approved_dates) if approved_dates else None
    cooldown_eligible = None if last_approved is None else last_approved + timedelta(days=rule["days"])
    checks = {
        "account_age": age_days >= rule["days"],
        "cooldown": last_approved is None or now >= cooldown_eligible,
        "no_active_dispute": data["has_active_dispute"] is False,
        "no_pending_replacement": data["has_pending_replacement"] is False,
        "good_standing": data["account_current"] is True and past_due == 0,
        "utilization": utilization < rule["utilization"],
        "payment_history": isinstance(data["consecutive_on_time_months"], int)
                           and data["consecutive_on_time_months"] >= rule["months"],
    }
    # Requested amount must be a positive whole dollar and no more than tier maximum.
    amount_valid = increase > 0 and increase == increase.to_integral_value() and increase <= max_increase
    failed = []
    reason_by_check = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("no_active_dispute", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    if not amount_valid:
        failed.append("requested_amount_exceeds_limit")
    failed.extend(reason for check, reason in reason_by_check if not checks[check])

    # An over-limit amount is handled before submission, not as a final denial.
    if not amount_valid:
        action = "needs_valid_amount"
    elif failed:
        action = "deny"
    else:
        action = "approve"
    return {
        "action": action,
        "tier": data["tier"],
        "missing_fields": [],
        "amount_within_limit": amount_valid,
        "checks": checks,
        "failed_reasons": failed,
        "primary_denial_reason": next((r for r in failed if r != "requested_amount_exceeds_limit"), None),
        "calculations": {
            "account_age_days": age_days,
            "minimum_age_days": rule["days"],
            "maximum_increase": str(max_increase),
            "new_credit_limit": str(limit + increase),
            "utilization_percent": str(utilization),
            "utilization_must_be_below_percent": str(rule["utilization"]),
            "required_on_time_months": rule["months"],
            "last_approved_cli_date": last_approved.isoformat() if last_approved else None,
            "cooldown_eligible_date": cooldown_eligible.isoformat() if cooldown_eligible else None,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"action": "needs_information", "missing_fields": [], "message": str(exc)}))
        sys.exit(2)
