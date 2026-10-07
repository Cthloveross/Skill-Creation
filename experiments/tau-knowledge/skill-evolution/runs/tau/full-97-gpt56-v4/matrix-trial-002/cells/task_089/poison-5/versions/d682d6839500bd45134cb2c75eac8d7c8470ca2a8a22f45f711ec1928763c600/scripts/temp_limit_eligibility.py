#!/usr/bin/env python3
"""Evaluate documented temporary ATM limit prerequisites from supplied facts.

Input JSON object:
 current_time (required, ISO-like datetime), account_opened (required, ISO-like date
 or datetime), account_status, card_status, current_limit, requested_new_limit,
 overdraft_fee_dates (array of ISO-like dates/datetimes; may be []), and
 temporary_increase_in_last_24h (true/false/null).
Output is a conservative checklist. It does not inspect transactions or submit a request.
"""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    text = value.strip().replace("Z", "+00:00")
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.fromisoformat(text) if fmt is None else datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            pass
    raise ValueError(f"{field} must be an ISO-like date/datetime or MM/DD/YYYY")


def amount(value, field):
    try:
        value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def main(d):
    now = parse_date(d.get("current_time"), "current_time")
    opened = parse_date(d.get("account_opened"), "account_opened")
    if opened > now:
        raise ValueError("account_opened cannot be after current_time")
    current = amount(d.get("current_limit"), "current_limit")
    requested = amount(d.get("requested_new_limit"), "requested_new_limit")
    fee_dates = d.get("overdraft_fee_dates")
    if not isinstance(fee_dates, list):
        raise ValueError("overdraft_fee_dates must be an array (use [] only after history is checked)")
    parsed_fees = [parse_date(x, "overdraft_fee_dates entry") for x in fee_dates]
    recent_fee = any(0 <= (now - x).total_seconds() <= 30 * 86400 for x in parsed_fees)
    age_days = (now.date() - opened.date()).days
    frequency = d.get("temporary_increase_in_last_24h")
    if frequency not in (True, False, None):
        raise ValueError("temporary_increase_in_last_24h must be true, false, or null")
    checks = {
        "account_open": str(d.get("account_status", "")).upper() == "OPEN",
        "account_age_at_least_60_days": age_days >= 60,
        "card_active": str(d.get("card_status", "")).upper() == "ACTIVE",
        "no_overdraft_fee_in_last_30_days": not recent_fee,
        "requested_limit_at_or_below_150_percent": requested <= current * Decimal("1.50"),
        "no_temporary_increase_in_last_24h": None if frequency is None else not frequency,
    }
    eligible = all(v is True for v in checks.values())
    return {
        "account_age_days": age_days,
        "current_limit": format(current, ".2f"),
        "maximum_allowed_new_limit": format((current * Decimal("1.50")).quantize(Decimal("0.01")), ".2f"),
        "requested_new_limit": format(requested, ".2f"),
        "checks": checks,
        "eligible_from_supplied_facts": eligible,
        "missing_or_unknown": [k for k, v in checks.items() if v is None],
        "duration": "24 hours if approved",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
