#!/usr/bin/env python3
"""Deterministically evaluate completed CLI eligibility facts.

Input: one JSON object on stdin. Output: one JSON object on stdout.
This program makes no network or banking-tool calls.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization": Decimal("70"), "payment_months": 6, "max_percent": Decimal("25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization": Decimal("80"), "payment_months": 3, "max_percent": Decimal("50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization": Decimal("90"), "payment_months": 3, "max_percent": Decimal("50")},
}


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        # Accept a date or an ISO timestamp; calendar-day rules use its date part.
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"{field} must be ISO formatted") from exc


def emit_error(message):
    print(json.dumps({"decision": "manual_review_required", "error": message}, sort_keys=True))


def main(data):
    tier = data.get("tier")
    if tier not in RULES:
        raise ValueError("tier must be entry, mid, or premium")
    rules = RULES[tier]
    current_limit = decimal_value(data.get("current_limit"), "current_limit")
    balance = decimal_value(data.get("current_balance"), "current_balance")
    if current_limit <= 0:
        raise ValueError("current_limit must be greater than zero")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    today = parse_date(data.get("now"), "now")
    if opened > today:
        raise ValueError("account_open_date cannot be after now")

    has_dollars = data.get("requested_increase_amount") is not None
    has_percent = data.get("requested_percent") is not None
    if has_dollars == has_percent:
        raise ValueError("provide exactly one of requested_increase_amount or requested_percent")
    if has_dollars:
        requested = decimal_value(data["requested_increase_amount"], "requested_increase_amount")
        request_source = "dollar_amount"
    else:
        percent = decimal_value(data["requested_percent"], "requested_percent")
        requested = current_limit * percent / Decimal("100")
        request_source = "percentage"

    max_increase = current_limit * rules["max_percent"] / Decimal("100")
    amount_status = "valid"
    if requested <= 0 or requested != requested.to_integral_value():
        amount_status = "needs_exact_whole_dollar_amount"
    elif requested > max_increase:
        amount_status = "exceeds_tier_maximum"

    age_days = (today - opened).days
    utilization = balance * Decimal("100") / current_limit
    prior_dates = data.get("prior_approved_request_dates")
    if not isinstance(prior_dates, list):
        raise ValueError("prior_approved_request_dates must be an array")
    approved_dates = [parse_date(item, "prior_approved_request_dates item") for item in prior_dates]
    latest_approved = max(approved_dates) if approved_dates else None
    cooldown_active = bool(latest_approved and today < latest_approved + timedelta(days=rules["cooldown_days"]))

    required_bools = ("account_current", "has_active_disputes", "has_pending_replacement", "payment_history_on_time")
    missing = [key for key in required_bools if not isinstance(data.get(key), bool)]
    past_due = decimal_value(data.get("past_due_amount"), "past_due_amount")
    if past_due < 0:
        raise ValueError("past_due_amount cannot be negative")

    failed = []
    if age_days < rules["age_days"]:
        failed.append("insufficient_account_age")
    if cooldown_active:
        failed.append("cooldown_period_active")
    if data.get("has_active_disputes") is True:
        failed.append("pending_disputes")
    if data.get("has_pending_replacement") is True:
        failed.append("pending_replacement_card")
    if data.get("account_current") is False or past_due > 0:
        failed.append("past_due_balance")
    if utilization >= rules["utilization"]:
        failed.append("high_utilization")
    if data.get("payment_history_on_time") is False:
        failed.append("insufficient_payment_history")

    if amount_status != "valid":
        decision = "obtain_valid_amount_before_submission"
    elif missing:
        decision = "manual_review_required"
    elif failed:
        decision = "deny"
    else:
        decision = "approve"

    output = {
        "tier": tier,
        "request_source": request_source,
        "requested_increase_amount": str(requested),
        "maximum_increase_amount": str(max_increase),
        "amount_status": amount_status,
        "new_credit_limit_if_approved": str(current_limit + requested),
        "account_age_days": age_days,
        "minimum_account_age_days": rules["age_days"],
        "utilization_percent": str(utilization),
        "utilization_must_be_below_percent": str(rules["utilization"]),
        "required_payment_months": rules["payment_months"],
        "latest_approved_request_date": latest_approved.isoformat() if latest_approved else None,
        "cooldown_days": rules["cooldown_days"],
        "cooldown_active": cooldown_active,
        "cooldown_eligible_date": (latest_approved + timedelta(days=rules["cooldown_days"])).isoformat() if latest_approved else None,
        "failed_checks": failed,
        "missing_or_invalid_check_facts": missing,
        "decision": decision,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        main(raw)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        emit_error(str(exc))
