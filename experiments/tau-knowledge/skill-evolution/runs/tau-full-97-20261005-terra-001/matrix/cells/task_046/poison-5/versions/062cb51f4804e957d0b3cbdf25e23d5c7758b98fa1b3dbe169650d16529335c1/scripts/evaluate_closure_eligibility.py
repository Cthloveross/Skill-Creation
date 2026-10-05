#!/usr/bin/env python3
"""Evaluate objective credit-card closure eligibility from JSON stdin.

Input:
  account_open_date: ISO date string (YYYY-MM-DD)
  as_of_date: ISO date string (YYYY-MM-DD)
  current_balance: decimal number or string
  has_pending_disputes: boolean or null
  replacement_orders: list of objects with a status field, or null

Output:
  eligible: bool
  blockers: list of machine-readable explanatory strings
  checks: object describing each check
  age_days: integer or null
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_balance(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        # Permit a conventional currency string but keep Decimal exactness.
        normalized = str(value).strip().replace("$", "").replace(",", "")
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def evaluate(payload):
    blockers = []
    checks = {}

    opened = parse_date(payload.get("account_open_date"))
    as_of = parse_date(payload.get("as_of_date"))
    age_days = None
    if opened is None or as_of is None:
        checks["account_age"] = "indeterminate"
        blockers.append("account_age_indeterminate")
    else:
        age_days = (as_of - opened).days
        if age_days < 0:
            checks["account_age"] = "invalid"
            blockers.append("account_age_invalid")
        elif age_days < 60:
            checks["account_age"] = "failed"
            blockers.append("account_under_60_days")
        else:
            checks["account_age"] = "passed"

    balance = parse_balance(payload.get("current_balance"))
    if balance is None:
        checks["zero_balance"] = "indeterminate"
        blockers.append("balance_indeterminate")
    elif balance != Decimal("0"):
        checks["zero_balance"] = "failed"
        blockers.append("outstanding_balance_not_zero")
    else:
        checks["zero_balance"] = "passed"

    disputes = payload.get("has_pending_disputes")
    if disputes is True:
        checks["pending_disputes"] = "failed"
        blockers.append("pending_disputes")
    elif disputes is False:
        checks["pending_disputes"] = "passed"
    else:
        checks["pending_disputes"] = "indeterminate"
        blockers.append("dispute_status_indeterminate")

    orders = payload.get("replacement_orders")
    if orders is None or not isinstance(orders, list):
        checks["replacement_orders"] = "indeterminate"
        blockers.append("replacement_order_status_indeterminate")
    else:
        nonfinal = []
        malformed = False
        for order in orders:
            if not isinstance(order, dict) or not isinstance(order.get("status"), str):
                malformed = True
                continue
            status = order["status"].strip().lower()
            if status not in FINAL_REPLACEMENT_STATUSES:
                nonfinal.append(status or "unknown")
        if malformed:
            checks["replacement_orders"] = "indeterminate"
            blockers.append("replacement_order_status_indeterminate")
        elif nonfinal:
            checks["replacement_orders"] = "failed"
            blockers.append("pending_replacement_card")
        else:
            checks["replacement_orders"] = "passed"

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "checks": checks,
        "age_days": age_days,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        result = evaluate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "eligible": False,
            "blockers": ["invalid_eligibility_input"],
            "checks": {"input": "invalid"},
            "age_days": None,
            "error": str(exc),
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
