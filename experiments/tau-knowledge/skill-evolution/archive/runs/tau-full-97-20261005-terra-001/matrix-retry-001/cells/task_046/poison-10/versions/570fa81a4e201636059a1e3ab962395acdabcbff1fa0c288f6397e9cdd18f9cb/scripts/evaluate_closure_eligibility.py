#!/usr/bin/env python3
"""Evaluate documented credit-card closure eligibility from supplied facts.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no I/O beyond stdin/stdout and never makes banking actions.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a nonempty date or timestamp string")
    text = value.strip()
    # Current-time tools commonly provide an ISO-like timestamp with a timezone label.
    candidates = [text, text[:10]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError(f"{field_name} must use YYYY-MM-DD, MM/DD/YYYY, or an ISO-like timestamp")


def parse_balance(value):
    if isinstance(value, bool):
        raise ValueError("current_balance must be a decimal amount, not a Boolean")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError("current_balance must be a decimal amount")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("current_balance is not a valid decimal amount")


def evaluate(payload):
    required = [
        "account_open_date",
        "current_balance",
        "pending_disputes",
        "replacement_orders",
        "as_of",
    ]
    missing = [name for name in required if name not in payload]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))

    opened = parse_date(payload["account_open_date"], "account_open_date")
    as_of = parse_date(payload["as_of"], "as_of")
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of")

    balance = parse_balance(payload["current_balance"])
    disputes = payload["pending_disputes"]
    if type(disputes) is not bool:
        raise ValueError("pending_disputes must be a Boolean")

    orders = payload["replacement_orders"]
    if not isinstance(orders, list):
        raise ValueError("replacement_orders must be an array")

    nonfinal_or_ambiguous = []
    for index, order in enumerate(orders):
        if not isinstance(order, dict):
            nonfinal_or_ambiguous.append({"index": index, "status": None})
            continue
        status = order.get("status")
        normalized = status.strip().casefold() if isinstance(status, str) else None
        if normalized not in FINAL_REPLACEMENT_STATUSES:
            nonfinal_or_ambiguous.append({"index": index, "status": status})

    age_days = (as_of - opened).days
    balance_is_zero = balance == Decimal("0")
    replacement_orders_clear = not nonfinal_or_ambiguous
    blockers = []
    if disputes:
        blockers.append("pending_disputes")
    if not replacement_orders_clear:
        blockers.append("pending_replacement_order")
    if age_days < 60:
        blockers.append("account_age_under_60_days")
    if not balance_is_zero:
        blockers.append("outstanding_balance_not_zero")

    return {
        "ok": True,
        "eligible": not blockers,
        "blockers": blockers,
        "account_age_days": age_days,
        "balance": format(balance, "f"),
        "balance_is_zero": balance_is_zero,
        "pending_disputes": disputes,
        "replacement_orders_clear": replacement_orders_clear,
        "nonfinal_or_ambiguous_orders": nonfinal_or_ambiguous,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(payload), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
