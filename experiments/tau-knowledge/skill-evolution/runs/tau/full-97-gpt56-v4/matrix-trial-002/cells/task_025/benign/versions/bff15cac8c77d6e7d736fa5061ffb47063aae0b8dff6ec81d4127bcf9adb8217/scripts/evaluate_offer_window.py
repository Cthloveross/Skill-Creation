#!/usr/bin/env python3
"""Evaluate date-window eligibility for a product offer from JSON stdin.

The caller must still establish new-customer, account-opening, approval, and
other non-date conditions. All dates are calendar dates in ISO YYYY-MM-DD.
"""
import json
import sys
from datetime import date


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO YYYY-MM-DD string") from exc


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be an object")
    current_date = parse_date(payload.get("current_date"), "current_date")
    start_date = parse_date(payload.get("start_date"), "start_date")
    end_date = parse_date(payload.get("end_date"), "end_date")
    if end_date < start_date:
        raise ValueError("end_date must not be earlier than start_date")
    account_open_date = payload.get("account_open_date")
    if account_open_date is None:
        opening_status = "unknown"
        relevant_date = current_date
    else:
        relevant_date = parse_date(account_open_date, "account_open_date")
        opening_status = "within_window" if start_date <= relevant_date <= end_date else "outside_window"
    return {
        "current_date": current_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "offer_window_status_on_current_date": "open" if start_date <= current_date <= end_date else "closed",
        "account_opening_status": opening_status,
        "date_condition_satisfied": opening_status == "within_window",
        "notice": "Date status alone does not establish account-opening completion, new-customer eligibility, approval, or any other offer condition."
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
