#!/usr/bin/env python3
"""Evaluate supplied credit-card closure facts without performing bank actions.

Read one JSON object from stdin and write one JSON object to stdout.
See SKILL.md for the input/output contract.
"""

import json
import re
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("current_balance must be numeric, not boolean")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        text = re.sub(r"^\$", "", text)
    else:
        raise ValueError("current_balance must be a number or currency string")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("current_balance is not a valid currency amount") from exc
    if amount < 0:
        raise ValueError("current_balance cannot be negative")
    return amount


def main(payload):
    required = {
        "today",
        "date_opened",
        "current_balance",
        "pending_disputes",
        "pending_replacement_cards",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

    today = parse_date(payload["today"], "today")
    opened = parse_date(payload["date_opened"], "date_opened")
    if opened > today:
        raise ValueError("date_opened cannot be after today")
    if not isinstance(payload["pending_disputes"], bool):
        raise ValueError("pending_disputes must be boolean")
    if not isinstance(payload["pending_replacement_cards"], bool):
        raise ValueError("pending_replacement_cards must be boolean")

    balance = parse_money(payload["current_balance"])
    age_days = (today - opened).days
    blockers = []
    if payload["pending_disputes"]:
        blockers.append("pending_disputes")
    if payload["pending_replacement_cards"]:
        blockers.append("pending_replacement_cards")
    if age_days < 60:
        blockers.append("account_under_60_days")
    if balance != Decimal("0.00"):
        blockers.append("nonzero_balance")

    return {
        "eligible": not blockers,
        "account_age_days": age_days,
        "balance": format(balance, ".2f"),
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")))
        sys.exit(2)
