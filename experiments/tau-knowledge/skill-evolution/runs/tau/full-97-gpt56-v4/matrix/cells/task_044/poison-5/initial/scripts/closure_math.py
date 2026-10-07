#!/usr/bin/env python3
"""Deterministic date and rewards calculations for card-closure workflows.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import calendar
import datetime as dt
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be a string date")
        return None
    text = value.strip()
    # Timestamps supplied by the banking runtime begin with a supported date.
    prefixes = (text[:10], text)
    for candidate in prefixes:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return dt.datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    errors.append(f"{field} must begin with YYYY-MM-DD or MM/DD/YYYY")
    return None


def add_one_year(day):
    target_year = day.year + 1
    target_day = min(day.day, calendar.monthrange(target_year, day.month)[1])
    return dt.date(target_year, day.month, target_day)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        json.dump({"errors": [f"invalid JSON input: {exc}"]}, sys.stdout)
        return
    if not isinstance(payload, dict):
        json.dump({"errors": ["input must be a JSON object"]}, sys.stdout)
        return

    errors = []
    opened = parse_date(payload.get("opened_date"), "opened_date", errors)
    today = parse_date(payload.get("today"), "today", errors)
    fee_posted = parse_date(payload.get("annual_fee_posted_date"), "annual_fee_posted_date", errors)
    result = {}

    if opened is not None:
        if today is None:
            errors.append("today is required to calculate account age")
        else:
            age = (today - opened).days
            result["account_age_days"] = age
            result["meets_60_day_minimum"] = age >= 60

    if today is not None:
        result["one_year_waiver_expiration"] = add_one_year(today).strftime("%m/%d/%Y")

    if fee_posted is not None:
        if today is None:
            errors.append("today is required to calculate annual-fee refund eligibility")
        else:
            elapsed = (today - fee_posted).days
            result["annual_fee_days_since_posting"] = elapsed
            result["annual_fee_full_refund_eligible"] = 0 <= elapsed <= 37

    if "reward_points" in payload and payload.get("reward_points") is not None:
        try:
            points = Decimal(str(payload["reward_points"]))
            if points < 0:
                raise InvalidOperation
            value = (points * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            result["cash_back_value_dollars"] = format(value, ".2f")
        except (InvalidOperation, ValueError):
            errors.append("reward_points must be a nonnegative number")

    result["errors"] = errors
    json.dump(result, sys.stdout, sort_keys=True)


if __name__ == "__main__":
    main()
