#!/usr/bin/env python3
"""Evaluate supplied credit-card closure eligibility facts.

Reads one JSON object from stdin and writes one JSON object to stdout. This
script is read-only: it does not query systems or perform account actions.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a non-empty string")
    text = value.strip()
    # Permit ISO date-time input by retaining the calendar-date portion.
    iso_part = text.split("T", 1)[0].split(" ", 1)[0]
    try:
        return datetime.strptime(iso_part, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError as exc:
            raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY") from exc


def parse_balance(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("current_balance must be a number or currency string")
    text = str(value).strip().replace("$", "").replace(",", "")
    if not text:
        raise ValueError("current_balance must not be empty")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid amount") from exc


def read_bool(data, key, blockers):
    value = data.get(key)
    if isinstance(value, bool):
        return value
    blockers.append({
        "code": "missing_" + key,
        "message": "Confirm " + key.replace("_", " ") + " before closure."
    })
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "needs_information", "error": "Invalid JSON: " + str(exc)}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"status": "needs_information", "error": "Input must be a JSON object."}))
        return

    blockers = []
    incomplete = False
    age_days = None

    try:
        opened = parse_date(data.get("opened_date"))
        as_of = parse_date(data.get("as_of_date"))
        age_days = (as_of - opened).days
        if age_days < 60:
            blockers.append({
                "code": "account_too_new",
                "message": "Account must be open for at least 60 days.",
                "account_age_days": age_days
            })
    except ValueError as exc:
        incomplete = True
        blockers.append({"code": "missing_or_invalid_account_age", "message": str(exc)})

    try:
        balance = parse_balance(data.get("current_balance"))
        if balance != Decimal("0"):
            blockers.append({
                "code": "nonzero_balance",
                "message": "Outstanding balance must be exactly $0.00 before closure.",
                "current_balance": format(balance, ".2f")
            })
    except ValueError as exc:
        incomplete = True
        blockers.append({"code": "missing_or_invalid_balance", "message": str(exc)})

    disputes = read_bool(data, "pending_disputes", blockers)
    replacement = read_bool(data, "pending_replacement_card", blockers)
    if disputes is None or replacement is None:
        incomplete = True
    elif disputes:
        blockers.append({
            "code": "pending_disputes",
            "message": "All active or pending transaction disputes must be resolved before closure."
        })
    if replacement is True:
        blockers.append({
            "code": "pending_replacement_card",
            "message": "Complete or cancel the pending replacement-card process before closure."
        })

    if incomplete:
        status = "needs_information"
    elif blockers:
        status = "ineligible"
    else:
        status = "eligible"

    result = {
        "status": status,
        "eligible_to_continue": status == "eligible",
        "account_age_days": age_days,
        "blockers": blockers
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
