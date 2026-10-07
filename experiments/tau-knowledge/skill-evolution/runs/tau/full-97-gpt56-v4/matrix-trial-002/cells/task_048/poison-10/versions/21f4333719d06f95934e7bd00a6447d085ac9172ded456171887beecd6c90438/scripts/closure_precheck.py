#!/usr/bin/env python3
"""Evaluate mechanical credit-card closure eligibility from supplied runtime facts.

Reads a single JSON object from stdin and writes a single JSON object to stdout.
No banking actions are performed by this helper.
"""

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "cancelled", "canceled"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty string")
    text = value.strip()
    # Timestamps supplied by banking tools commonly begin with ISO date.
    iso_match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if iso_match:
        return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
    for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format")


def parse_money(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("current_balance must be a number or currency string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    # Permit a surrounding textual currency label but reject embedded numbers.
    cleaned = re.sub(r"\s*(USD|dollars?)\s*$", "", cleaned, flags=re.I)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid amount") from exc


def status_of(record):
    if not isinstance(record, dict):
        return ""
    value = record.get("status", "")
    return str(value).strip().lower()


def main(payload):
    required = [
        "as_of",
        "date_of_account_open",
        "current_balance",
        "target_disputes",
        "replacement_orders",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        return {"input_valid": False, "eligible": False, "errors": ["missing: " + ", ".join(missing)]}

    errors = []
    try:
        as_of = parse_date(payload["as_of"])
        opened = parse_date(payload["date_of_account_open"])
        balance = parse_money(payload["current_balance"])
    except ValueError as exc:
        return {"input_valid": False, "eligible": False, "errors": [str(exc)]}

    disputes = payload["target_disputes"]
    orders = payload["replacement_orders"]
    if not isinstance(disputes, list):
        errors.append("target_disputes must be a list")
    if not isinstance(orders, list):
        errors.append("replacement_orders must be a list")
    if opened > as_of:
        errors.append("account opening date is after as_of date")
    if errors:
        return {"input_valid": False, "eligible": False, "errors": errors}

    age_days = (as_of - opened).days
    active_disputes = [record for record in disputes if status_of(record) not in FINAL_DISPUTE_STATUSES]
    nonfinal_orders = [record for record in orders if status_of(record) not in FINAL_ORDER_STATUSES]

    blockers = []
    if balance != Decimal("0"):
        blockers.append("nonzero_balance")
    if age_days < 60:
        blockers.append("account_under_60_days")
    if active_disputes:
        blockers.append("active_or_pending_target_dispute")
    if nonfinal_orders:
        blockers.append("pending_replacement_order")

    return {
        "input_valid": True,
        "eligible": not blockers,
        "account_age_days": age_days,
        "balance_is_zero": balance == Decimal("0"),
        "active_target_dispute_count": len(active_disputes),
        "nonfinal_replacement_order_count": len(nonfinal_orders),
        "blockers": blockers,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("stdin JSON must be an object")
        output = main(incoming)
    except Exception as exc:  # Keep the documented JSON stdout contract on bad input.
        output = {"input_valid": False, "eligible": False, "errors": [str(exc)]}
    print(json.dumps(output, default=str, sort_keys=True))
