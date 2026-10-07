#!/usr/bin/env python3
"""Validate documented personal checking closure prerequisites.

Read a JSON object from stdin and write one JSON object to stdout. This script
performs no bank action.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


TIERS = {
    "Light Blue Account": (Decimal("15"), 30, 0),
    "Light Green Account": (Decimal("15"), 30, 0),
    "Green Fee-Free Account": (Decimal("15"), 30, 0),
    "Blue Account": (Decimal("25"), 60, 3),
    "Green Account (checking)": (Decimal("25"), 60, 3),
    "Evergreen Account": (Decimal("50"), 90, 7),
    "Bluest Account": (Decimal("100"), 180, 14),
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def money(value):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("balance must be numeric")
    if not parsed.is_finite():
        raise ValueError("balance must be finite")
    return parsed


def decimal_text(value):
    return format(value.quantize(Decimal("0.01")), "f")


def check(payload):
    reasons = []
    account_class = payload.get("account_class")
    tier = TIERS.get(account_class)
    fee = Decimal("0")
    fee_window_days = None
    notice_days = None
    days_open = None
    in_early_fee_window = None

    if tier is None:
        reasons.append("unsupported or missing account_class")
    else:
        fee, fee_window_days, notice_days = tier

    if payload.get("status") != "OPEN":
        reasons.append("account status must be OPEN")

    pending = payload.get("has_pending_transactions")
    if pending is not False:
        reasons.append("pending-transaction status must be confirmed false")

    balance = None
    try:
        balance = money(payload.get("balance"))
    except ValueError as exc:
        reasons.append(str(exc))

    try:
        opened = parse_date(payload.get("opening_date"))
        current = parse_date(payload.get("current_date"))
        days_open = (current - opened).days
        if days_open < 0:
            reasons.append("opening_date cannot be after current_date")
    except ValueError as exc:
        reasons.append(str(exc))

    if tier is not None and days_open is not None and days_open >= 0:
        # "within N days" is interpreted as fewer than N elapsed calendar days.
        in_early_fee_window = days_open < fee_window_days

    if balance is not None and in_early_fee_window is not None:
        if in_early_fee_window:
            if balance < fee:
                reasons.append("balance is less than the applicable early-closure fee")
        elif balance != Decimal("0"):
            reasons.append("balance must be exactly zero outside the early-fee window")

    return {
        "eligible": not reasons,
        "account_class": account_class,
        "fee": decimal_text(fee),
        "fee_window_days": fee_window_days,
        "notice_days": notice_days,
        "days_open": days_open,
        "in_early_fee_window": in_early_fee_window,
        "blocking_reasons": reasons,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = check(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "eligible": False,
            "fee": "0.00",
            "fee_window_days": None,
            "notice_days": None,
            "days_open": None,
            "in_early_fee_window": None,
            "blocking_reasons": ["invalid input: " + str(exc)],
        }
    json.dump(result, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
