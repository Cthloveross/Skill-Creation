#!/usr/bin/env python3
"""Evaluate credit-card closure facts received as one JSON object on stdin.

Input schema:
{
  "as_of": "YYYY-MM-DD",
  "opened_on": "YYYY-MM-DD",
  "balance": number|string,
  "disputes": [{"status": string}, ...],  # selected-card disputes only
  "replacement_orders": [{"status": string}, ...]
}
Output schema:
{"eligible": bool, "blockers": [str], "account_age_days": int|null,
 "checks": {"zero_balance": bool, "minimum_age": bool,
            "no_pending_disputes": bool, "no_pending_replacements": bool}}
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

FINAL_ORDER_STATUSES = {"delivered", "cancelled"}
CLOSED_DISPUTE_STATUSES = {"closed", "resolved", "withdrawn"}


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def main(data):
    """Evaluate facts already scoped to the selected credit-card account."""
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    as_of = parse_date(data.get("as_of"), "as_of")
    opened = parse_date(data.get("opened_on"), "opened_on")
    if opened > as_of:
        raise ValueError("opened_on cannot be after as_of")
    try:
        balance = Decimal(str(data.get("balance")))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("balance must be numeric") from exc
    if not balance.is_finite():
        raise ValueError("balance must be finite")

    disputes = data.get("disputes", [])
    orders = data.get("replacement_orders", [])
    if not isinstance(disputes, list) or not isinstance(orders, list):
        raise ValueError("disputes and replacement_orders must be lists")
    if any(not isinstance(x, dict) or not isinstance(x.get("status"), str) for x in disputes):
        raise ValueError("each dispute needs a string status")
    if any(not isinstance(x, dict) or not isinstance(x.get("status"), str) for x in orders):
        raise ValueError("each replacement order needs a string status")

    age_days = (as_of - opened).days
    zero = balance == Decimal("0")
    old_enough = age_days >= 60
    no_disputes = all(x["status"].strip().lower() in CLOSED_DISPUTE_STATUSES for x in disputes)
    no_orders = all(x["status"].strip().lower() in FINAL_ORDER_STATUSES for x in orders)
    blockers = []
    if not zero:
        blockers.append("outstanding_balance_not_zero")
    if not old_enough:
        blockers.append("account_younger_than_60_days")
    if not no_disputes:
        blockers.append("pending_or_active_dispute")
    if not no_orders:
        blockers.append("pending_replacement_order")
    checks = {
        "zero_balance": zero,
        "minimum_age": old_enough,
        "no_pending_disputes": no_disputes,
        "no_pending_replacements": no_orders,
    }
    return {"eligible": not blockers, "blockers": blockers, "account_age_days": age_days, "checks": checks}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")))
        sys.exit(2)
