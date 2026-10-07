#!/usr/bin/env python3
"""Evaluate explicit credit-card closure prerequisites from JSON stdin.

This helper does not query banking systems and never performs a bank action.
Input schema and output schema are documented in ../SKILL.md.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    # Timestamps such as "2025-01-15 03:40:00 EST" have a parseable prefix.
    for prefix, fmt in ((text[:10], "%Y-%m-%d"), (text[:10], "%m/%d/%Y")):
        try:
            return datetime.strptime(prefix, fmt).date()
        except ValueError:
            pass
    return None


def parse_balance(value):
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"eligible": False, "blockers": ["invalid_input_json: " + str(exc)], "account_age_days": None, "normalized_balance": None}))
        return

    blockers = []
    current = parse_date(data.get("current_date"))
    opened = parse_date(data.get("date_of_account_open"))
    age_days = None
    if current is None or opened is None:
        blockers.append("account_age_unconfirmed: current_date and date_of_account_open must be valid dates")
    else:
        age_days = (current - opened).days
        if age_days < 60:
            blockers.append("account_too_new: account must be open at least 60 days")

    disputes = data.get("pending_disputes")
    if disputes is True:
        blockers.append("pending_disputes: resolve all active or pending disputes before closure")
    elif disputes is not False:
        blockers.append("dispute_status_unconfirmed")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        blockers.append("replacement_order_status_unconfirmed")
    else:
        nonfinal = []
        for order in orders:
            status = order.get("status") if isinstance(order, dict) else None
            if not isinstance(status, str) or status.strip().lower() not in {"delivered", "cancelled", "canceled"}:
                nonfinal.append(status if status is not None else "unknown")
        if nonfinal:
            blockers.append("pending_replacement_order: all replacement orders must be delivered or cancelled")

    balance = parse_balance(data.get("current_balance"))
    if balance is None:
        blockers.append("balance_unconfirmed")
        normalized = None
    else:
        normalized = format(balance, ".2f")
        if balance != Decimal("0.00"):
            blockers.append("nonzero_balance: outstanding balance must be exactly $0.00")

    result = {
        "eligible": not blockers,
        "blockers": blockers,
        "account_age_days": age_days,
        "normalized_balance": normalized,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
