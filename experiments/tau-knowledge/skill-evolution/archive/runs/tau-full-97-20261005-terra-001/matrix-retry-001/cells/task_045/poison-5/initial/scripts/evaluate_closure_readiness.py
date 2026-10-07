#!/usr/bin/env python3
"""Evaluate factual credit-card closure prerequisites from JSON stdin.

Input:
{
  "as_of_date": "YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD",
  "balance": number,
  "target_active_disputes": [{"dispute_id": str, "status": str}],
  "replacement_orders": [{"order_id": str, "status": str}]
}

Output:
{
  "eligible": bool,
  "account_age_days": int | null,
  "blockers": [str],
  "replacement_order_review": [{"order_id": str | null, "status": str}]
}
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("balance must be numeric") from exc


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(data.get("as_of_date"), "as_of_date")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of_date")
    balance = money(data.get("balance"))

    disputes = data.get("target_active_disputes", [])
    orders = data.get("replacement_orders", [])
    if not isinstance(disputes, list) or not isinstance(orders, list):
        raise ValueError("target_active_disputes and replacement_orders must be arrays")

    blockers = []
    age_days = (as_of - opened).days
    if age_days < 60:
        blockers.append("account_age_under_60_days")
    if balance != Decimal("0"):
        blockers.append("nonzero_outstanding_balance")
    if disputes:
        blockers.append("active_or_pending_target_card_dispute")

    reviewed_orders = []
    nonfinal_order = False
    for order in orders:
        if not isinstance(order, dict):
            raise ValueError("each replacement order must be an object")
        status = str(order.get("status", "")).strip().lower()
        reviewed_orders.append({"order_id": order.get("order_id"), "status": status})
        if status not in FINAL_REPLACEMENT_STATUSES:
            nonfinal_order = True
    if nonfinal_order:
        blockers.append("pending_replacement_card")

    return {
        "eligible": not blockers,
        "account_age_days": age_days,
        "blockers": blockers,
        "replacement_order_review": reviewed_orders,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
