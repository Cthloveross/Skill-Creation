#!/usr/bin/env python3
"""Deterministic date and reward calculations for the closure workflow.

Reads one JSON object from stdin and writes one JSON object to stdout.
No account data is read and no banking action is taken.
"""
import datetime as dt
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty string")
    text = value.strip()
    # Timestamps supplied by the banking runtime begin with a date; isolate it.
    token = text.split()[0]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(token, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format; use YYYY-MM-DD or MM/DD/YYYY")


def one_calendar_year_after(day):
    try:
        return day.replace(year=day.year + 1)
    except ValueError:  # February 29 becomes February 28 in a non-leap year.
        return day.replace(year=day.year + 1, month=2, day=28)


def main(payload):
    opened = parse_date(payload.get("account_open_date"))
    today = parse_date(payload.get("current_time"))
    age_days = (today - opened).days
    if age_days < 0:
        raise ValueError("account_open_date cannot be after current_time")

    output = {
        "account_age_days": age_days,
        "meets_60_day_minimum": age_days >= 60,
        "one_year_from_current_date": one_calendar_year_after(today).strftime("%m/%d/%Y"),
    }

    if "reward_points" in payload:
        try:
            points = Decimal(str(payload["reward_points"]))
        except (InvalidOperation, ValueError):
            raise ValueError("reward_points must be numeric")
        if points < 0:
            raise ValueError("reward_points cannot be negative")
        if payload.get("cash_back_at_one_cent") is True:
            value = (points * Decimal("0.01")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            output["cash_value"] = format(value, ".2f")
            output["cash_value_currency"] = "USD"

    if payload.get("annual_fee_posted_date") not in (None, ""):
        fee_date = parse_date(payload["annual_fee_posted_date"])
        days_since = (today - fee_date).days
        output["annual_fee_days_since_posting"] = days_since
        output["within_37_day_annual_fee_refund_window"] = 0 <= days_since <= 37

    return output


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
