#!/usr/bin/env python3
"""Evaluate normalized credit-limit-increase facts supplied as JSON on stdin."""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

RULES = {
    "entry": {
        "maximum_increase_fraction": Decimal("0.25"),
        "minimum_account_age_days": 120,
        "cooldown_days": 120,
        "utilization_threshold_percent": Decimal("70"),
        "required_on_time_months": 6,
    },
    "mid": {
        "maximum_increase_fraction": Decimal("0.50"),
        "minimum_account_age_days": 90,
        "cooldown_days": 90,
        "utilization_threshold_percent": Decimal("80"),
        "required_on_time_months": 3,
    },
    "premium": {
        "maximum_increase_fraction": Decimal("0.50"),
        "minimum_account_age_days": 60,
        "cooldown_days": 60,
        "utilization_threshold_percent": Decimal("90"),
        "required_on_time_months": 3,
    },
}

DENIAL_PRIORITY = [
    "insufficient_account_age",
    "cooldown_period_active",
    "pending_disputes",
    "pending_replacement_card",
    "past_due_balance",
    "high_utilization",
    "insufficient_payment_history",
]


def money(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{field} must be a numeric value")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def parse_date(value, field, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a nonempty date string")
        return None
    text = value.strip()
    # Timestamps supplied by the runtime begin with an ISO calendar date.
    candidates = [text, text[:10]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    errors.append(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")
    return None


def required_bool(data, key, errors):
    value = data.get(key)
    if type(value) is not bool:
        errors.append(f"{key} must be boolean")
        return None
    return value


def main(data):
    errors = []
    mode = data.get("mode")
    if mode not in ("pre_submission", "full"):
        errors.append("mode must be 'pre_submission' or 'full'")

    tier = str(data.get("tier", "")).strip().lower().replace("-tier", "")
    rules = RULES.get(tier)
    if rules is None:
        errors.append("tier must be entry, mid, or premium")

    requested = money(data.get("requested_increase_amount"), "requested_increase_amount", errors)
    limit = money(data.get("current_credit_limit"), "current_credit_limit", errors)
    if requested is not None:
        if requested <= 0 or requested != requested.to_integral_value():
            errors.append("requested_increase_amount must be a positive whole-dollar amount")
    if limit is not None and limit <= 0:
        errors.append("current_credit_limit must be greater than zero")

    result = {
        "errors": errors,
        "tier": tier,
        "maximum_increase_amount": None,
        "new_credit_limit": None,
        "pre_submission_valid": False,
        "decision": "incomplete",
        "denial_reason": None,
        "failed_checks": [],
    }
    if rules:
        result.update({
            "maximum_increase_fraction": str(rules["maximum_increase_fraction"]),
            "minimum_account_age_days": rules["minimum_account_age_days"],
            "cooldown_days": rules["cooldown_days"],
            "utilization_threshold_percent": float(rules["utilization_threshold_percent"]),
            "required_on_time_months": rules["required_on_time_months"],
        })

    if errors:
        return result

    # Requests are integer dollars. Flooring prevents a fractional percentage cap
    # from accidentally authorizing an amount above the policy cap.
    maximum = (limit * rules["maximum_increase_fraction"]).quantize(
        Decimal("1"), rounding=ROUND_FLOOR
    )
    result["maximum_increase_amount"] = int(maximum)
    result["new_credit_limit"] = float(limit + requested)
    amount_valid = requested <= maximum
    result["pre_submission_valid"] = bool(amount_valid)
    if not amount_valid:
        result["decision"] = "needs_customer_adjustment"
        result["denial_reason"] = "requested_amount_exceeds_limit"
        result["failed_checks"] = ["requested_amount_exceeds_limit"]
        return result

    if mode == "pre_submission":
        result["decision"] = "ready_to_submit"
        return result

    as_of = parse_date(data.get("as_of"), "as_of", errors)
    opened = parse_date(data.get("account_open_date"), "account_open_date", errors)
    approved_raw = data.get("last_approved_cli_date")
    approved = None
    if approved_raw is not None:
        approved = parse_date(approved_raw, "last_approved_cli_date", errors)
    balance = money(data.get("current_balance"), "current_balance", errors)
    past_due = money(data.get("past_due_amount"), "past_due_amount", errors)
    active_disputes = required_bool(data, "has_active_disputes", errors)
    pending_replacement = required_bool(data, "has_pending_replacement", errors)
    payment_months = data.get("consecutive_on_time_months")
    if type(payment_months) is not int or payment_months < 0:
        errors.append("consecutive_on_time_months must be a nonnegative integer")

    if errors:
        return result
    if approved is not None and approved > as_of:
        result["errors"].append("last_approved_cli_date cannot be after as_of")
        return result

    age_days = (as_of - opened).days
    cooldown_elapsed = None if approved is None else (as_of - approved).days
    utilization = (balance / limit) * Decimal("100")
    result.update({
        "age_days": age_days,
        "cooldown_days_elapsed": cooldown_elapsed,
        "utilization_percent": float(utilization),
    })

    failed = []
    if age_days < rules["minimum_account_age_days"]:
        failed.append("insufficient_account_age")
    if cooldown_elapsed is not None and cooldown_elapsed < rules["cooldown_days"]:
        failed.append("cooldown_period_active")
    if active_disputes:
        failed.append("pending_disputes")
    if pending_replacement:
        failed.append("pending_replacement_card")
    if past_due > 0:
        failed.append("past_due_balance")
    if utilization >= rules["utilization_threshold_percent"]:
        failed.append("high_utilization")
    if payment_months < rules["required_on_time_months"]:
        failed.append("insufficient_payment_history")

    result["failed_checks"] = failed
    if not failed:
        result["decision"] = "approve"
        return result

    result["decision"] = "deny"
    result["denial_reason"] = next(reason for reason in DENIAL_PRIORITY if reason in failed)
    return result


def emit(payload):
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            emit({"errors": ["input must be a JSON object"], "decision": "incomplete"})
        else:
            emit(main(raw))
    except json.JSONDecodeError:
        emit({"errors": ["stdin must contain valid JSON"], "decision": "incomplete"})
