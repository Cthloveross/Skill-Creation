#!/usr/bin/env python3
"""Evaluate normalized CLI eligibility data supplied as JSON on stdin.

This script is deliberately side-effect free. It never invokes bank tools and its
output is a recommendation for the execution agent, not a recorded decision.
"""
import json
import sys
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

RULES = {
    "entry": {"age_days": 120, "cooldown_days": 120, "utilization": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid": {"age_days": 90, "cooldown_days": 90, "utilization": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium": {"age_days": 60, "cooldown_days": 60, "utilization": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}
REASON_ORDER = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("disputes", "pending_disputes"),
    ("replacement_orders", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]


def parse_datetime(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date/time value must be a nonempty string")
    value = value.strip()
    try:
        if len(value) == 10:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError("invalid ISO-8601 date/time: %s" % value) from exc


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError("%s must be numeric" % field)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("%s must be numeric" % field) from exc


def tier_name(value):
    if not isinstance(value, str):
        raise ValueError("tier must be entry, mid, or premium")
    normalized = value.strip().lower().replace("_", "-")
    if normalized.endswith("-tier"):
        normalized = normalized[:-5]
    if normalized not in RULES:
        raise ValueError("tier must be entry, mid, or premium")
    return normalized


def list_or_unknown(value, field):
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("%s must be a list or null" % field)
    return value


def approved_cooldown(history, now, days):
    if history is None:
        return None
    approved_dates = []
    for record in history:
        if not isinstance(record, dict) or "status" not in record or "submitted_at" not in record:
            return None
        if str(record["status"]).strip().lower() == "approved":
            try:
                approved_dates.append(parse_datetime(record["submitted_at"]))
            except ValueError:
                return None
    if not approved_dates:
        return True
    latest = max(approved_dates)
    # Negative elapsed time is conservatively treated as an active cooldown.
    return (now - latest).total_seconds() >= days * 86400


def no_active_disputes(disputes):
    if disputes is None:
        return None
    for record in disputes:
        if not isinstance(record, dict) or "status" not in record:
            return None
        if str(record["status"]).strip().lower() != "closed":
            return False
    return True


def no_pending_replacements(orders):
    if orders is None:
        return None
    final_states = {"delivered", "cancelled", "canceled"}
    for record in orders:
        if not isinstance(record, dict) or "status" not in record:
            return None
        if str(record["status"]).strip().lower() not in final_states:
            return False
    return True


def consecutive_on_time(history, required_months):
    if history is None:
        return None
    if len(history) < required_months:
        return False
    for item in history[:required_months]:
        if isinstance(item, bool):
            on_time = item
        elif isinstance(item, dict) and isinstance(item.get("on_time"), bool):
            on_time = item["on_time"]
        else:
            return None
        if not on_time:
            return False
    return True


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be a JSON object")
    tier = tier_name(payload.get("tier"))
    rules = RULES[tier]
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    now = parse_datetime(payload.get("now"))
    opened = parse_datetime(account.get("opened_on"))
    limit = decimal_value(account.get("current_limit"), "account.current_limit")
    balance = decimal_value(account.get("current_balance"), "account.current_balance")
    past_due = decimal_value(account.get("past_due_amount"), "account.past_due_amount")
    if limit <= 0:
        raise ValueError("account.current_limit must be greater than zero")

    amount_raw = payload.get("requested_increase_amount")
    amount = decimal_value(amount_raw, "requested_increase_amount")
    is_whole_dollar = amount == amount.to_integral_value()
    max_increase = limit * rules["max_fraction"]
    base = {
        "tier": tier,
        "max_increase": float(max_increase),
        "requested_increase_amount": float(amount),
    }
    if amount <= 0 or not is_whole_dollar or amount > max_increase:
        base.update({
            "decision": "adjust_amount",
            "new_credit_limit": None,
            "denial_reason": None,
            "checks": {"requested_amount": False},
            "message": "A positive whole-dollar amount at or below max_increase is required before submission.",
        })
        return base

    history = list_or_unknown(payload.get("history"), "history")
    disputes = list_or_unknown(payload.get("disputes"), "disputes")
    orders = list_or_unknown(payload.get("replacement_orders"), "replacement_orders")
    payments = list_or_unknown(payload.get("payment_history"), "payment_history")
    checks = {
        "requested_amount": True,
        "account_age": (now.date() - opened.date()).days >= rules["age_days"],
        "cooldown": approved_cooldown(history, now, rules["cooldown_days"]),
        "disputes": no_active_disputes(disputes),
        "replacement_orders": no_pending_replacements(orders),
        "good_standing": past_due <= 0,
        "utilization": (balance / limit * Decimal("100")) < rules["utilization"],
        "payment_history": consecutive_on_time(payments, rules["payment_months"]),
    }
    base["checks"] = checks
    if any(value is None for value in checks.values()):
        base.update({
            "decision": "incomplete",
            "new_credit_limit": None,
            "denial_reason": None,
            "message": "Resolve every check whose value is null before recording a decision.",
        })
        return base
    for check, reason in REASON_ORDER:
        if checks[check] is False:
            base.update({
                "decision": "deny",
                "new_credit_limit": None,
                "denial_reason": reason,
                "message": "All checks were evaluated; the selected reason follows the documented stable priority.",
            })
            return base
    base.update({
        "decision": "approve",
        "new_credit_limit": float(limit + amount),
        "denial_reason": None,
        "message": "All required normalized checks passed. The execution agent must still call the approval tool.",
    })
    return base


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
