#!/usr/bin/env python3
"""Conservative mechanical checks for a credit-card closure.

Input JSON schema:
{
  "as_of": "YYYY-MM-DD or timestamp beginning YYYY-MM-DD",
  "account_open_date": "YYYY-MM-DD or MM/DD/YYYY",
  "current_balance": "0.00" | number,
  "dispute_statuses": ["closed", ...],
  "replacement_order_statuses": ["delivered", ...]
}

Output JSON schema:
{
  "eligible": bool,
  "age_days": int | null,
  "blockers": [string, ...],
  "validation_errors": [string, ...]
}

Unknown dispute and order statuses are deliberately blockers. The caller must prefilter
user-level dispute history to disputes that are known to concern the selected account;
if that cannot be done safely, pass an explicit unknown status.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "cancelled", "canceled", "withdrawn"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value, field, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required and must be a date string")
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            pass
    errors.append(f"{field} has an unsupported date format")
    return None


def status_list(value, field, errors):
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    statuses = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field} contains an invalid status")
        else:
            statuses.append(item.strip().lower())
    return statuses


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"eligible": False, "age_days": None,
                          "blockers": ["input could not be read"],
                          "validation_errors": [str(exc)]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"eligible": False, "age_days": None,
                          "blockers": ["input must be a JSON object"],
                          "validation_errors": ["top-level JSON value is not an object"]}))
        return

    errors, blockers = [], []
    as_of = parse_date(payload.get("as_of"), "as_of", errors)
    opened = parse_date(payload.get("account_open_date"), "account_open_date", errors)

    age_days = None
    if as_of and opened:
        age_days = (as_of - opened).days
        if age_days < 0:
            errors.append("account_open_date is after as_of")
        elif age_days < 60:
            blockers.append("account age is less than 60 days")

    balance = payload.get("current_balance")
    try:
        # Decimal(str(...)) avoids binary float comparison artifacts.
        amount = Decimal(str(balance).replace("$", "").replace(",", "").strip())
        if amount != Decimal("0"):
            blockers.append("outstanding balance is not zero")
    except (InvalidOperation, AttributeError):
        errors.append("current_balance must be a numeric value")

    disputes = status_list(payload.get("dispute_statuses"), "dispute_statuses", errors)
    for status in disputes:
        if status not in FINAL_DISPUTE_STATUSES:
            blockers.append(f"unresolved or unknown dispute status: {status}")

    orders = status_list(payload.get("replacement_order_statuses"), "replacement_order_statuses", errors)
    for status in orders:
        if status not in FINAL_ORDER_STATUSES:
            blockers.append(f"pending or unknown replacement order status: {status}")

    result = {
        "eligible": not errors and not blockers,
        "age_days": age_days,
        "blockers": blockers,
        "validation_errors": errors,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
