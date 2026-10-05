#!/usr/bin/env python3
"""Evaluate known closure prerequisites from a JSON object on stdin.

Input:
{
  "as_of_date": "YYYY-MM-DD",
  "date_of_account_open": "YYYY-MM-DD",
  "current_balance": "0.00" | 0 | "$0.00",
  "disputes_scope_confirmed": true | false,
  "account_dispute_statuses": ["closed", ...],
  "replacement_orders_checked": true | false,
  "replacement_order_statuses": ["delivered", "cancelled", ...]
}
Output: {"eligible": bool, "account_age_days": int|null, "blockers": [string]}

This intentionally fails closed on missing/malformed information.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "finalized"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a YYYY-MM-DD string")
    return date.fromisoformat(value)


def parse_money(value):
    if isinstance(value, str):
        value = value.strip().replace("$", "").replace(",", "")
    return Decimal(str(value))


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
    except Exception as exc:
        print(json.dumps({"eligible": False, "account_age_days": None,
                          "blockers": [f"invalid input: {exc}"]}))
        return

    blockers = []
    age_days = None
    try:
        age_days = (parse_date(data.get("as_of_date")) -
                    parse_date(data.get("date_of_account_open"))).days
        if age_days < 60:
            blockers.append("account age is less than 60 days")
    except Exception:
        blockers.append("account opening date or current date is missing or invalid")

    try:
        if parse_money(data.get("current_balance")) != Decimal("0"):
            blockers.append("outstanding balance is not zero")
    except (InvalidOperation, ValueError, TypeError):
        blockers.append("outstanding balance is missing or invalid")

    if data.get("disputes_scope_confirmed") is not True:
        blockers.append("dispute scope for the selected account is not confirmed")
    statuses = data.get("account_dispute_statuses")
    if not isinstance(statuses, list):
        blockers.append("account dispute statuses are missing or invalid")
    else:
        nonfinal = [str(s) for s in statuses if str(s).strip().lower() not in FINAL_DISPUTE_STATUSES]
        if nonfinal:
            blockers.append("selected account has active or unresolved dispute status: " + ", ".join(nonfinal))

    if data.get("replacement_orders_checked") is not True:
        blockers.append("replacement-order check has not been completed")
    order_statuses = data.get("replacement_order_statuses")
    if not isinstance(order_statuses, list):
        blockers.append("replacement-order statuses are missing or invalid")
    else:
        nonfinal = [str(s) for s in order_statuses if str(s).strip().lower() not in FINAL_REPLACEMENT_STATUSES]
        if nonfinal:
            blockers.append("pending or non-final replacement order status: " + ", ".join(nonfinal))

    print(json.dumps({"eligible": not blockers, "account_age_days": age_days,
                      "blockers": blockers}))


if __name__ == "__main__":
    main()
