#!/usr/bin/env python3
"""Conservatively evaluate temporary ATM-limit prerequisites from supplied facts.

JSON stdin fields: current_time, account_opened, account_status, card_status,
current_limit, requested_new_limit, overdraft_fee_dates (array),
overdraft_history_checked (bool), and temporary_increase_in_last_24h
(true/false/null). Dates accept ISO-like strings, MM/DD/YYYY, and
'YYYY-MM-DD HH:MM:SS EST/EDT'. JSON stdout is a checklist; this script never
retrieves records or submits a banking request.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    text = value.strip()
    zones = {" EST": timezone(timedelta(hours=-5)), " EDT": timezone(timedelta(hours=-4))}
    for suffix, zone in zones.items():
        if text.endswith(suffix):
            try:
                return datetime.strptime(text[:-len(suffix)], "%Y-%m-%d %H:%M:%S").replace(tzinfo=zone)
            except ValueError:
                raise ValueError(f"{field} has an invalid runtime timestamp")
    normalized = text.replace("Z", "+00:00")
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            parsed = datetime.fromisoformat(normalized) if fmt is None else datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"{field} must be an ISO-like date/datetime, MM/DD/YYYY, or runtime timestamp")


def amount(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal amount")
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be nonnegative")
    return result


def main(d):
    now = parse_date(d.get("current_time"), "current_time")
    opened = parse_date(d.get("account_opened"), "account_opened")
    if opened > now:
        raise ValueError("account_opened cannot be after current_time")
    current = amount(d.get("current_limit"), "current_limit")
    requested = amount(d.get("requested_new_limit"), "requested_new_limit")
    fee_dates = d.get("overdraft_fee_dates")
    if not isinstance(fee_dates, list):
        raise ValueError("overdraft_fee_dates must be an array")
    history_checked = d.get("overdraft_history_checked")
    if not isinstance(history_checked, bool):
        raise ValueError("overdraft_history_checked must be true or false")
    fees = [parse_date(x, "overdraft_fee_dates entry") for x in fee_dates]
    recent_fee = any(0 <= (now - fee).total_seconds() <= 30 * 86400 for fee in fees)
    frequency = d.get("temporary_increase_in_last_24h")
    if frequency not in (True, False, None):
        raise ValueError("temporary_increase_in_last_24h must be true, false, or null")
    checks = {
        "account_open": str(d.get("account_status", "")).upper() == "OPEN",
        "account_age_at_least_60_days": (now.date() - opened.date()).days >= 60,
        "card_active": str(d.get("card_status", "")).upper() == "ACTIVE",
        "overdraft_history_checked": history_checked,
        "no_overdraft_fee_in_last_30_days": None if not history_checked else not recent_fee,
        "requested_limit_at_or_below_150_percent": requested <= current * Decimal("1.50"),
        "no_temporary_increase_in_last_24h": None if frequency is None else not frequency,
    }
    return {
        "account_age_days": (now.date() - opened.date()).days,
        "current_limit": format(current, ".2f"),
        "maximum_allowed_new_limit": format((current * Decimal("1.50")).quantize(Decimal("0.01")), ".2f"),
        "requested_new_limit": format(requested, ".2f"),
        "checks": checks,
        "eligible_from_supplied_facts": all(item is True for item in checks.values()),
        "missing_or_unknown": [name for name, item in checks.items() if item is None],
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
