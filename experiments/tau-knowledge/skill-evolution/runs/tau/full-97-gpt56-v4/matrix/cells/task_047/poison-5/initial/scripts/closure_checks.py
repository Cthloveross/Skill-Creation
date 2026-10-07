#!/usr/bin/env python3
"""Conservative deterministic assessment for credit-card closure prerequisites.

Reads JSON from stdin and prints JSON. This script does not call banking tools and
is intentionally conservative: unknown dispute/order statuses require review.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")
CLEAR_DISPUTE = {"closed", "resolved", "completed", "dismissed"}
BLOCKING_DISPUTE = {"open", "pending", "under_review", "active", "in_review"}
FINAL_ORDERS = {"delivered", "cancelled", "canceled"}
BLOCKING_ORDERS = {"pending", "shipped", "processing", "active", "in_transit", "ordered"}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a date string")
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    errors.append(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")
    return None


def parse_balance(value, errors):
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        errors.append("current_balance is not a valid monetary amount")
        return None


def statuses(value, field, errors):
    if value is None:
        errors.append(f"{field} is required; use [] only for an authoritative empty result")
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        errors.append(f"{field} must be an array of status strings")
        return None
    return [x.strip().lower().replace(" ", "_") for x in value]


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"eligible": False, "account_age_days": None,
                          "blockers": [], "errors": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"eligible": False, "account_age_days": None,
                          "blockers": [], "errors": ["input must be a JSON object"]}))
        return

    errors, blockers = [], []
    today = parse_date(data.get("current_date"), "current_date", errors)
    opened = parse_date(data.get("date_of_account_open"), "date_of_account_open", errors)
    balance = parse_balance(data.get("current_balance"), errors)
    disputes = statuses(data.get("target_dispute_statuses"), "target_dispute_statuses", errors)
    orders = statuses(data.get("replacement_order_statuses"), "replacement_order_statuses", errors)

    age_days = None
    if today and opened:
        age_days = (today - opened).days
        if age_days < 0:
            errors.append("date_of_account_open is after current_date")
        elif age_days < 60:
            blockers.append("account_age_under_60_days")

    if balance is not None and balance != Decimal("0"):
        blockers.append("nonzero_outstanding_balance")

    if disputes is not None:
        for status in disputes:
            if status in BLOCKING_DISPUTE:
                blockers.append("active_or_pending_dispute")
                break
            if status not in CLEAR_DISPUTE:
                blockers.append("unresolved_dispute_status")
                break

    if orders is not None:
        for status in orders:
            if status in BLOCKING_ORDERS:
                blockers.append("pending_replacement_order")
                break
            if status not in FINAL_ORDERS:
                blockers.append("unresolved_replacement_order_status")
                break

    output = {
        "eligible": not errors and not blockers,
        "account_age_days": age_days,
        "blockers": blockers,
        "errors": errors,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
