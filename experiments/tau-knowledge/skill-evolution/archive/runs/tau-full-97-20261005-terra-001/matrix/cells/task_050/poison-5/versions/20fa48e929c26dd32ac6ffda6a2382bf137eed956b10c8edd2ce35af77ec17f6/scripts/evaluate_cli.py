#!/usr/bin/env python3
"""Evaluate normalized credit-limit-increase eligibility data.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
performs no banking-tool calls and cannot create, approve, or deny a CLI request.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payments": 6, "fraction": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payments": 3, "fraction": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payments": 3, "fraction": Decimal("0.50")},
}
ALIASES = {
    "entry": "entry", "entry-tier": "entry", "entry_tier": "entry",
    "mid": "mid", "mid-tier": "mid", "mid_tier": "mid",
    "premium": "premium", "premium-tier": "premium", "premium_tier": "premium",
}
DENIALS = (
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement", "pending_replacement_card"),
    ("standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
)


def incomplete(errors, extra=None):
    output = {
        "recommendation": "incomplete",
        "denial_reason": None,
        "errors": errors,
        "checks": {},
        "maximum_increase": None,
        "new_credit_limit": None,
        "utilization_percent": None,
        "next_eligible_on": None,
    }
    if extra:
        output.update(extra)
    return output


def parse_date(value):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("must be a string beginning YYYY-MM-DD")
    return date.fromisoformat(value[:10])


def decimal(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(label + " must be numeric")
    if not result.is_finite():
        raise ValueError(label + " must be finite")
    return result


def money(value):
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def evaluate(payload):
    if not isinstance(payload, dict):
        return incomplete(["input must be a JSON object"])
    account = payload.get("account")
    if not isinstance(account, dict):
        return incomplete(["account must be an object"])

    errors = []
    raw_tier = account.get("tier")
    tier = ALIASES.get(str(raw_tier).strip().lower()) if raw_tier is not None else None
    if tier is None:
        errors.append("account.tier must be entry, mid, or premium")
    try:
        today = parse_date(payload.get("current_time"))
    except ValueError as exc:
        errors.append("current_time " + str(exc))
        today = None
    try:
        opened = parse_date(account.get("opened_on"))
    except ValueError as exc:
        errors.append("account.opened_on " + str(exc))
        opened = None
    try:
        limit = decimal(account.get("current_credit_limit"), "account.current_credit_limit")
        if limit <= 0:
            errors.append("account.current_credit_limit must be greater than zero")
    except ValueError as exc:
        errors.append(str(exc))
        limit = None
    try:
        balance = decimal(account.get("current_balance"), "account.current_balance")
        if balance < 0:
            errors.append("account.current_balance cannot be negative")
    except ValueError as exc:
        errors.append(str(exc))
        balance = None
    try:
        requested = decimal(payload.get("requested_increase_amount"), "requested_increase_amount")
        if requested <= 0 or requested != requested.to_integral_value():
            errors.append("requested_increase_amount must be a positive whole-dollar amount")
    except ValueError as exc:
        errors.append(str(exc))
        requested = None
    if errors:
        return incomplete(errors)

    rule = RULES[tier]
    maximum = (limit * rule["fraction"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    utilization = balance / limit * Decimal("100")
    base = {
        "tier": tier,
        "errors": [],
        "maximum_increase": money(maximum),
        "new_credit_limit": money(limit + requested),
        "utilization_percent": money(utilization),
        "next_eligible_on": None,
    }
    if requested > maximum:
        base.update({
            "recommendation": "do_not_submit",
            "denial_reason": "requested_amount_exceeds_limit",
            "checks": {"requested_amount": False},
        })
        return base

    if not isinstance(account.get("past_due"), bool):
        errors.append("account.past_due must be an explicit boolean")
    for key in ("has_active_disputes", "has_pending_replacement"):
        if not isinstance(payload.get(key), bool):
            errors.append(key + " must be an explicit boolean")
    payment = payload.get("payment_history")
    months = payment.get("consecutive_on_time_months") if isinstance(payment, dict) else None
    if isinstance(months, bool) or not isinstance(months, int) or months < 0:
        errors.append("payment_history.consecutive_on_time_months must be a nonnegative integer")
    history = payload.get("prior_requests")
    if not isinstance(history, list):
        errors.append("prior_requests must be a list of requests before the current submission")
    if errors:
        return incomplete(errors, base)

    parsed_history = []
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            return incomplete(["prior_requests[%d] must be an object" % index], base)
        try:
            submitted = parse_date(record.get("submitted_at"))
        except ValueError as exc:
            return incomplete(["prior_requests[%d].submitted_at %s" % (index, exc)], base)
        status = record.get("status")
        if not isinstance(status, str) or not status.strip():
            return incomplete(["prior_requests[%d].status must be a nonempty string" % index], base)
        parsed_history.append((submitted, status.strip().lower()))

    if opened > today:
        return incomplete(["account.opened_on cannot be in the future"], base)

    approved_dates = [submitted for submitted, status in parsed_history if status == "approved"]
    cooldown_ok = True
    if approved_dates:
        latest_approved = max(approved_dates)
        eligible_on = latest_approved + timedelta(days=rule["cooldown"])
        base["next_eligible_on"] = eligible_on.isoformat()
        cooldown_ok = today >= eligible_on

    checks = {
        "requested_amount": True,
        "account_age": (today - opened).days >= rule["age"],
        "cooldown": cooldown_ok,
        "disputes": not payload["has_active_disputes"],
        "replacement": not payload["has_pending_replacement"],
        "standing": not account["past_due"],
        "utilization": utilization < rule["utilization"],
        "payment_history": months >= rule["payments"],
    }
    base["account_age_days"] = (today - opened).days
    base["checks"] = checks
    for check, reason in DENIALS:
        if not checks[check]:
            base.update({"recommendation": "deny", "denial_reason": reason})
            return base
    base.update({"recommendation": "approve", "denial_reason": None})
    return base


if __name__ == "__main__":
    try:
        result = evaluate(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        result = incomplete(["invalid JSON input: " + str(exc)])
    except Exception as exc:
        result = incomplete(["unexpected evaluation error: " + str(exc)])
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
