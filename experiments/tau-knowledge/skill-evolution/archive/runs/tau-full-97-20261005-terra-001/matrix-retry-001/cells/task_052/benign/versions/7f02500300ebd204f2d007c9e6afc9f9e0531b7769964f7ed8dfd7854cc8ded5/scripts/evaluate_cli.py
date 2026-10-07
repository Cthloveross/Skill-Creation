#!/usr/bin/env python3
"""Deterministically assess normalized CLI facts read as one JSON object on stdin.

This helper has no banking-tool integration. It returns JSON on stdout and is intended
for use after the executor has performed the required lookups and normalized them.
"""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization": Decimal("70"), "payments": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization": Decimal("80"), "payments": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization": Decimal("90"), "payments": 3, "max_fraction": Decimal("0.50")},
}
ALIASES = {
    "entry-tier": "entry", "mid-tier": "mid", "premium-tier": "premium",
    "entry tier": "entry", "mid tier": "mid", "premium tier": "premium",
}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def decimal_value(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("%s must be numeric" % field)


def parse_date(value, field):
    if value is None or value == "":
        return None
    text = str(value).strip()
    for candidate in (text, text[:10]):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        raise ValueError("%s is not a supported date" % field)


def money_text(amount):
    return format(amount.quantize(Decimal("0.01")), "f")


def main(data):
    tier_text = str(data.get("tier", "")).strip().lower()
    tier = ALIASES.get(tier_text, tier_text)
    if tier not in RULES:
        raise ValueError("tier must be entry, mid, or premium")
    rule = RULES[tier]

    limit = decimal_value(data.get("current_limit"), "current_limit")
    balance = decimal_value(data.get("current_balance"), "current_balance")
    past_due = decimal_value(data.get("past_due_amount"), "past_due_amount")
    if limit <= 0:
        raise ValueError("current_limit must be greater than zero")

    has_amount = data.get("requested_increase_amount") is not None
    has_percent = data.get("requested_increase_percent") is not None
    if has_amount == has_percent:
        raise ValueError("provide exactly one requested increase amount or percent")
    if has_amount:
        requested = decimal_value(data["requested_increase_amount"], "requested_increase_amount")
    else:
        percent = decimal_value(data["requested_increase_percent"], "requested_increase_percent")
        requested = limit * percent / Decimal("100")

    max_increase = limit * rule["max_fraction"]
    integer_dollars = requested == requested.to_integral_value()
    valid_positive_amount = requested > 0
    amount_within_maximum = requested <= max_increase
    may_submit = valid_positive_amount and integer_dollars and amount_within_maximum

    output = {
        "tier": tier,
        "calculation": {
            "current_limit": money_text(limit),
            "requested_increase": money_text(requested),
            "maximum_increase": money_text(max_increase),
            "new_credit_limit": money_text(limit + requested),
            "requested_amount_is_whole_dollars": integer_dollars,
        },
        "pre_submit": {
            "may_submit": may_submit,
            "reason": None,
        },
        "eligibility": {"complete": False, "checks": {}},
        "decision": "needs_review",
        "denial_reason": None,
        "next_eligible_submission_date": None,
    }
    if not valid_positive_amount:
        output["pre_submit"]["reason"] = "requested increase must be greater than zero"
        output["decision"] = "request_clarification"
        return output
    if not integer_dollars:
        output["pre_submit"]["reason"] = "submission requires an exact whole-dollar increase"
        output["decision"] = "request_clarification"
        return output
    if not amount_within_maximum:
        output["pre_submit"]["reason"] = "requested amount exceeds tier maximum; do not submit"
        output["decision"] = "request_adjustment"
        return output

    today = parse_date(data.get("current_date"), "current_date")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    approved_date = parse_date(data.get("last_approved_submission_date"), "last_approved_submission_date")
    if today is None or opened is None:
        raise ValueError("current_date and account_open_date are required after submission")

    age = (today - opened).days
    utilization = balance * Decimal("100") / limit
    cooldown_end = approved_date + timedelta(days=rule["cooldown_days"]) if approved_date else None
    cooldown_ok = cooldown_end is None or today >= cooldown_end

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        raise ValueError("replacement_orders must be an array")
    pending_replacement = any(
        str(order.get("status", "")).strip().lower() not in FINAL_REPLACEMENT_STATUSES
        for order in orders
        if isinstance(order, dict)
    )
    if any(not isinstance(order, dict) for order in orders):
        raise ValueError("each replacement order must be an object")

    try:
        payment_months = int(data.get("consecutive_on_time_months"))
    except (TypeError, ValueError):
        raise ValueError("consecutive_on_time_months must be an integer")
    if not isinstance(data.get("active_disputes"), bool):
        raise ValueError("active_disputes must be boolean")

    checks = {
        "account_age": {"pass": age >= rule["age_days"], "observed_days": age, "required_days": rule["age_days"]},
        "cooldown": {"pass": cooldown_ok, "required_days": rule["cooldown_days"], "last_approved_submission_date": approved_date.isoformat() if approved_date else None},
        "disputes": {"pass": not data["active_disputes"]},
        "replacement_card": {"pass": not pending_replacement},
        "good_standing": {"pass": past_due <= 0, "past_due_amount": money_text(past_due)},
        "utilization": {"pass": utilization < rule["utilization"], "utilization_percent": str(utilization), "must_be_below_percent": str(rule["utilization"])},
        "payment_history": {"pass": payment_months >= rule["payments"], "consecutive_on_time_months": payment_months, "required_months": rule["payments"]},
    }
    output["eligibility"]["checks"] = checks
    complete = bool(data.get("checks_complete", False))
    output["eligibility"]["complete"] = complete
    if cooldown_end:
        output["next_eligible_submission_date"] = cooldown_end.isoformat()
    if not complete:
        return output

    reason_order = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("disputes", "pending_disputes"),
        ("replacement_card", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    for check_name, denial_reason in reason_order:
        if not checks[check_name]["pass"]:
            output["decision"] = "deny"
            output["denial_reason"] = denial_reason
            return output
    output["decision"] = "approve"
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin must contain one JSON object")
        print(json.dumps(main(payload), sort_keys=True, separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
