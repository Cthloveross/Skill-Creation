#!/usr/bin/env python3
"""Evaluate normalized CLI facts supplied as one JSON object on stdin.

This program performs no banking action. Input fields are documented in SKILL.md.
Dates may be ISO dates/timestamps or MM/DD/YYYY. Output is one JSON object.
"""
import json
import math
import sys
from datetime import datetime, timedelta

RULES = {
    "entry": {"age": 120, "cooldown": 120, "utilization": 70.0, "payments": 6, "max_fraction": 0.25},
    "mid": {"age": 90, "cooldown": 90, "utilization": 80.0, "payments": 3, "max_fraction": 0.50},
    "premium": {"age": 60, "cooldown": 60, "utilization": 90.0, "payments": 3, "max_fraction": 0.50},
}
PRECEDENCE = [
    "insufficient_account_age", "cooldown_period_active", "pending_disputes",
    "pending_replacement_card", "past_due_balance", "high_utilization",
    "insufficient_payment_history", "requested_amount_exceeds_limit",
]

def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date is missing")
    value = value.strip()
    # Time zone labels are not needed for whole-day eligibility arithmetic.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(value[:26], fmt).date()
        except ValueError:
            pass
    # Handles strings such as '2025-11-14 03:40:00 EST'.
    try:
        return datetime.strptime(value.rsplit(" ", 1)[0], "%Y-%m-%d %H:%M:%S").date()
    except ValueError as exc:
        raise ValueError("unsupported date format: %s" % value) from exc

def number(data, key, errors):
    try:
        value = float(data[key])
        if not math.isfinite(value):
            raise ValueError()
        return value
    except (KeyError, TypeError, ValueError):
        errors.append("%s must be a finite number" % key)
        return None

def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"eligible": False, "errors": ["invalid JSON: %s" % exc]}))
        return
    errors = []
    tier = str(data.get("tier", "")).strip().lower().replace("-tier", "")
    if tier not in RULES:
        errors.append("tier must be entry, mid, or premium")
        rule = None
    else:
        rule = RULES[tier]
    limit = number(data, "current_limit", errors)
    increase = number(data, "requested_increase", errors)
    balance = number(data, "current_balance", errors)
    past_due = number(data, "past_due_amount", errors)
    payments = number(data, "on_time_months", errors)
    opened = now = None
    try:
        opened = parse_date(data.get("account_open_date"))
    except ValueError as exc:
        errors.append(str(exc).replace("date", "account_open_date", 1))
    try:
        now = parse_date(data.get("now"))
    except ValueError as exc:
        errors.append(str(exc).replace("date", "now", 1))

    max_increase = None
    new_limit = None
    amount_valid = False
    if limit is not None and limit > 0 and rule:
        max_increase = limit * rule["max_fraction"]
        if increase is not None:
            amount_valid = increase > 0 and increase.is_integer() and increase <= max_increase
            if amount_valid:
                new_limit = limit + increase
    elif limit is not None and limit <= 0:
        errors.append("current_limit must be greater than zero")

    checks = {}
    failed = []
    if rule and opened and now:
        checks["account_age"] = (now - opened).days >= rule["age"]
        if not checks["account_age"]:
            failed.append("insufficient_account_age")

    latest = None
    dates = data.get("approved_request_dates", [])
    if not isinstance(dates, list):
        errors.append("approved_request_dates must be a list")
    else:
        for raw in dates:
            try:
                candidate = parse_date(raw)
                if latest is None or candidate > latest:
                    latest = candidate
            except ValueError:
                errors.append("approved_request_dates contains an unsupported date")
                break
    if rule and now and isinstance(dates, list) and not any(e.startswith("approved_request_dates") for e in errors):
        next_date = latest + timedelta(days=rule["cooldown"]) if latest else None
        checks["cooldown"] = latest is None or now >= next_date
        if not checks["cooldown"]:
            failed.append("cooldown_period_active")
    else:
        next_date = None

    for field in ("has_active_disputes", "has_pending_replacement", "account_current"):
        if field not in data or not isinstance(data.get(field), bool):
            errors.append("%s must be boolean" % field)
    if isinstance(data.get("has_active_disputes"), bool):
        checks["disputes"] = not data["has_active_disputes"]
        if not checks["disputes"]:
            failed.append("pending_disputes")
    if isinstance(data.get("has_pending_replacement"), bool):
        checks["replacement"] = not data["has_pending_replacement"]
        if not checks["replacement"]:
            failed.append("pending_replacement_card")
    if past_due is not None and isinstance(data.get("account_current"), bool):
        checks["standing"] = data["account_current"] and past_due <= 0
        if not checks["standing"]:
            failed.append("past_due_balance")
    if rule and limit is not None and limit > 0 and balance is not None:
        utilization = balance / limit * 100.0
        checks["utilization"] = utilization < rule["utilization"]
        if not checks["utilization"]:
            failed.append("high_utilization")
    else:
        utilization = None
    if rule and payments is not None:
        checks["payment_history"] = payments >= rule["payments"]
        if not checks["payment_history"]:
            failed.append("insufficient_payment_history")
    checks["requested_amount"] = amount_valid
    if not amount_valid and increase is not None and limit is not None and rule:
        failed.append("requested_amount_exceeds_limit")

    # Preserve a stable, documented order and suppress accidental duplicates.
    failed = [reason for reason in PRECEDENCE if reason in failed]
    eligible = not errors and not failed
    result = {
        "tier": tier,
        "maximum_increase": max_increase,
        "new_credit_limit": new_limit,
        "utilization_percent": utilization,
        "amount_valid": amount_valid,
        "checks": checks,
        "failed_reasons": failed,
        "eligible": eligible,
        "denial_reason": None if eligible else (failed[0] if failed else "other"),
        "errors": errors,
    }
    if next_date is not None:
        result["next_eligible_date"] = next_date.isoformat()
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
