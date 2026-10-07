#!/usr/bin/env python3
"""Deterministically evaluate normalized CLI eligibility data.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
never calls tools and never performs an account action.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry": {"min_age": 120, "cooldown": 120, "utilization": Decimal("70"), "payments": 6, "max_fraction": Decimal("0.25")},
    "mid": {"min_age": 90, "cooldown": 90, "utilization": Decimal("80"), "payments": 3, "max_fraction": Decimal("0.50")},
    "premium": {"min_age": 60, "cooldown": 60, "utilization": Decimal("90"), "payments": 3, "max_fraction": Decimal("0.50")},
}
TIER_ALIASES = {
    "entry": "entry", "entry-tier": "entry", "entry_tier": "entry",
    "mid": "mid", "mid-tier": "mid", "mid_tier": "mid",
    "premium": "premium", "premium-tier": "premium", "premium_tier": "premium",
}
FINAL_DENIAL_ORDER = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement", "pending_replacement_card"),
    ("standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]


def parse_date(value):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("date must be a string beginning YYYY-MM-DD")
    return date.fromisoformat(value[:10])


def money(value, field):
    if isinstance(value, bool):
        raise ValueError(field + " must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be numeric")
    if not result.is_finite():
        raise ValueError(field + " must be finite")
    return result


def decimal_output(value):
    # JSON numbers, rounded only for monetary display/calculation boundaries.
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def incomplete(errors, base=None):
    out = {
        "recommendation": "incomplete",
        "denial_reason": None,
        "errors": errors,
        "checks": {},
        "maximum_increase": None,
        "new_credit_limit": None,
        "utilization_percent": None,
        "next_eligible_on": None,
    }
    if base:
        out.update(base)
    return out


def main(data):
    errors = []
    if not isinstance(data, dict):
        return incomplete(["input must be a JSON object"])
    account = data.get("account")
    if not isinstance(account, dict):
        return incomplete(["account object is required"])

    tier_raw = account.get("tier")
    tier = TIER_ALIASES.get(str(tier_raw).strip().lower()) if tier_raw is not None else None
    if tier is None:
        errors.append("account.tier must be entry, mid, or premium")
    try:
        today = parse_date(data.get("current_time"))
    except ValueError as exc:
        errors.append("current_time: " + str(exc))
        today = None
    try:
        opened = parse_date(account.get("opened_on"))
    except ValueError as exc:
        errors.append("account.opened_on: " + str(exc))
        opened = None
    try:
        limit = money(account.get("current_credit_limit"), "account.current_credit_limit")
        if limit <= 0:
            errors.append("account.current_credit_limit must be greater than zero")
    except ValueError as exc:
        errors.append(str(exc))
        limit = None
    try:
        balance = money(account.get("current_balance"), "account.current_balance")
        if balance < 0:
            errors.append("account.current_balance cannot be negative")
    except ValueError as exc:
        errors.append(str(exc))
        balance = None

    requested_raw = data.get("requested_increase_amount")
    try:
        requested = money(requested_raw, "requested_increase_amount")
        if requested <= 0 or requested != requested.to_integral_value():
            errors.append("requested_increase_amount must be a positive whole-dollar amount")
    except ValueError as exc:
        errors.append(str(exc))
        requested = None

    if errors:
        return incomplete(errors)

    rule = RULES[tier]
    maximum = (limit * rule["max_fraction"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    new_limit = limit + requested
    base = {
        "tier": tier,
        "maximum_increase": decimal_output(maximum),
        "new_credit_limit": decimal_output(new_limit),
        "utilization_percent": decimal_output((balance / limit) * Decimal("100")),
        "next_eligible_on": None,
    }

    # This pre-submission validation intentionally precedes all post-submission checks.
    if requested > maximum:
        base.update({
            "recommendation": "do_not_submit",
            "denial_reason": "requested_amount_exceeds_limit",
            "errors": [],
            "checks": {"requested_amount": False},
        })
        return base

    # All fields below are mandatory after a valid request has been submitted.
    missing = []
    if not isinstance(account.get("past_due"), bool):
        missing.append("account.past_due must be an explicit boolean")
    if not isinstance(data.get("has_active_disputes"), bool):
        missing.append("has_active_disputes must be an explicit boolean")
    if not isinstance(data.get("has_pending_replacement"), bool):
        missing.append("has_pending_replacement must be an explicit boolean")
    payments = data.get("payment_history")
    if not isinstance(payments, dict) or isinstance(payments.get("consecutive_on_time_months"), bool) or not isinstance(payments.get("consecutive_on_time_months"), int) or payments.get("consecutive_on_time_months") < 0:
        missing.append("payment_history.consecutive_on_time_months must be a nonnegative integer")
    history = data.get("prior_requests")
    if not isinstance(history, list):
        missing.append("prior_requests must be a list of pre-existing requests")
    if missing:
        return incomplete(missing, base)

    parsed_history = []
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            return incomplete(["prior_requests[%d] must be an object" % index], base)
        try:
            submitted = parse_date(record.get("submitted_at"))
        except ValueError as exc:
            return incomplete(["prior_requests[%d].submitted_at: %s" % (index, exc)], base)
        status = record.get("status")
        if not isinstance(status, str) or not status.strip():
            return incomplete(["prior_requests[%d].status must be a nonempty string" % index], base)
        parsed_history.append((submitted, status.strip().lower()))

    if opened > today:
        return incomplete(["account.opened_on is in the future"], base)
    age_days = (today - opened).days
    latest = max(parsed_history, key=lambda entry: entry[0]) if parsed_history else None
    next_eligible = None
    cooldown_ok = True
    # Only the most recent prior approved request creates a cooldown.
    if latest and latest[1] == "approved":
        next_eligible = latest[0] + timedelta(days=rule["cooldown"])
        cooldown_ok = today >= next_eligible

    checks = {
        "requested_amount": True,
        "account_age": age_days >= rule["min_age"],
        "cooldown": cooldown_ok,
        "disputes": not data["has_active_disputes"],
        "replacement": not data["has_pending_replacement"],
        "standing": not account["past_due"],
        "utilization": ((balance / limit) * Decimal("100")) < rule["utilization"],
        "payment_history": payments["consecutive_on_time_months"] >= rule["payments"],
    }
    base["checks"] = checks
    base["errors"] = []
    base["account_age_days"] = age_days
    if next_eligible is not None:
        base["next_eligible_on"] = next_eligible.isoformat()

    for check_name, reason in FINAL_DENIAL_ORDER:
        if not checks[check_name]:
            base["recommendation"] = "deny"
            base["denial_reason"] = reason
            return base
    base["recommendation"] = "approve"
    base["denial_reason"] = None
    return base


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
    except json.JSONDecodeError as exc:
        result = incomplete(["invalid JSON input: " + str(exc)])
    except Exception as exc:  # Ensure callers receive JSON rather than a traceback.
        result = incomplete(["unexpected evaluation error: " + str(exc)])
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
