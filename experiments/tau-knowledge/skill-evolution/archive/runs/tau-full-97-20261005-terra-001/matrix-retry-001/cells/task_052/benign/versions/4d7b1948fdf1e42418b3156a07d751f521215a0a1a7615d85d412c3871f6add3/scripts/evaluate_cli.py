#!/usr/bin/env python3
"""Evaluate normalized CLI facts from JSON stdin without making banking-tool calls."""
import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

RULES = {
    "entry": {"age": 120, "cooldown": 120, "util": Decimal("70"), "payments": 6, "cap": Decimal("0.25")},
    "mid": {"age": 90, "cooldown": 90, "util": Decimal("80"), "payments": 3, "cap": Decimal("0.50")},
    "premium": {"age": 60, "cooldown": 60, "util": Decimal("90"), "payments": 3, "cap": Decimal("0.50")},
}
ALIASES = {"entry-tier": "entry", "mid-tier": "mid", "premium-tier": "premium"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled"}


def dec(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(field + " must be numeric")


def date(value, field, nullable=False):
    if value is None or value == "":
        if nullable:
            return None
        raise ValueError(field + " is required")
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
        raise ValueError(field + " is not a supported date")


def money(value):
    return format(value.quantize(Decimal("0.01")), "f")


def main(data):
    tier = ALIASES.get(str(data.get("tier", "")).strip().lower(), str(data.get("tier", "")).strip().lower())
    if tier not in RULES:
        raise ValueError("tier must be entry, mid, or premium")
    rule = RULES[tier]
    limit = dec(data.get("current_limit"), "current_limit")
    balance = dec(data.get("current_balance"), "current_balance")
    past_due = dec(data.get("past_due_amount"), "past_due_amount")
    if limit <= 0:
        raise ValueError("current_limit must be greater than zero")

    has_amount = data.get("requested_increase_amount") is not None
    has_percent = data.get("requested_increase_percent") is not None
    if has_amount == has_percent:
        raise ValueError("provide exactly one requested increase amount or percent")
    requested = dec(data["requested_increase_amount"], "requested_increase_amount") if has_amount else limit * dec(data["requested_increase_percent"], "requested_increase_percent") / Decimal("100")
    maximum = limit * rule["cap"]
    whole = requested == requested.to_integral_value()
    valid = requested > 0 and whole and requested <= maximum
    output = {
        "tier": tier,
        "calculation": {"current_limit": money(limit), "requested_increase": money(requested), "maximum_increase": money(maximum), "new_credit_limit": money(limit + requested), "requested_amount_is_whole_dollars": whole},
        "pre_submit": {"may_submit": valid, "reason": None},
        "eligibility": {"complete": False, "checks": {}},
        "decision": "needs_review", "denial_reason": None, "next_eligible_submission_date": None,
    }
    if requested <= 0:
        output["pre_submit"]["reason"] = "requested increase must be greater than zero"
        output["decision"] = "request_clarification"
        return output
    if not whole:
        output["pre_submit"]["reason"] = "submission requires a whole-dollar increase"
        output["decision"] = "request_clarification"
        return output
    if requested > maximum:
        output["pre_submit"]["reason"] = "requested amount exceeds tier maximum; do not submit"
        output["decision"] = "request_adjustment"
        return output

    today = date(data.get("current_date"), "current_date")
    opened = date(data.get("account_open_date"), "account_open_date")
    prior = date(data.get("last_approved_submission_date"), "last_approved_submission_date", True)
    if not isinstance(data.get("active_disputes"), bool):
        raise ValueError("active_disputes must be boolean")
    orders = data.get("replacement_orders")
    if not isinstance(orders, list) or any(not isinstance(order, dict) for order in orders):
        raise ValueError("replacement_orders must be an array of objects")
    try:
        payment_months = int(data.get("consecutive_on_time_months"))
    except (TypeError, ValueError):
        raise ValueError("consecutive_on_time_months must be an integer")

    age = (today - opened).days
    utilization = balance * Decimal("100") / limit
    cooldown_end = prior + timedelta(days=rule["cooldown"]) if prior else None
    pending_order = any(str(order.get("status", "")).strip().lower() not in FINAL_ORDER_STATUSES for order in orders)
    checks = {
        "account_age": {"pass": age >= rule["age"], "observed_days": age, "required_days": rule["age"]},
        "cooldown": {"pass": cooldown_end is None or today >= cooldown_end, "last_approved_submission_date": prior.isoformat() if prior else None, "required_days": rule["cooldown"]},
        "disputes": {"pass": not data["active_disputes"]},
        "replacement_card": {"pass": not pending_order},
        "good_standing": {"pass": past_due <= 0, "past_due_amount": money(past_due)},
        "utilization": {"pass": utilization < rule["util"], "utilization_percent": str(utilization), "must_be_below_percent": str(rule["util"])},
        "payment_history": {"pass": payment_months >= rule["payments"], "consecutive_on_time_months": payment_months, "required_months": rule["payments"]},
    }
    output["eligibility"] = {"complete": bool(data.get("checks_complete", False)), "checks": checks}
    output["next_eligible_submission_date"] = cooldown_end.isoformat() if cooldown_end else None
    if not output["eligibility"]["complete"]:
        return output
    for check, reason in (("account_age", "insufficient_account_age"), ("cooldown", "cooldown_period_active"), ("disputes", "pending_disputes"), ("replacement_card", "pending_replacement_card"), ("good_standing", "past_due_balance"), ("utilization", "high_utilization"), ("payment_history", "insufficient_payment_history")):
        if not checks[check]["pass"]:
            output["decision"] = "deny"
            output["denial_reason"] = reason
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
