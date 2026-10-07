#!/usr/bin/env python3
"""Emit the annual-fee-waiver expiration date one calendar year after input date.

Reads JSON from stdin: {"current_time": "YYYY-MM-DD ..."}
Writes JSON to stdout: {"expiration_date": "MM/DD/YYYY"}
"""
import calendar
import datetime as dt
import json
import re
import sys


def expiration_date(current_time: str) -> str:
    if not isinstance(current_time, str):
        raise ValueError("current_time must be a string")
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:$|[ T])", current_time.strip())
    if not match:
        raise ValueError("current_time must begin with YYYY-MM-DD")
    year, month, day = (int(part) for part in match.groups())
    # Validate the source date and clamp only the target leap-day case.
    dt.date(year, month, day)
    target_year = year + 1
    target_day = min(day, calendar.monthrange(target_year, month)[1])
    return dt.date(target_year, month, target_day).strftime("%m/%d/%Y")


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps({"expiration_date": expiration_date(payload.get("current_time"))}))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
