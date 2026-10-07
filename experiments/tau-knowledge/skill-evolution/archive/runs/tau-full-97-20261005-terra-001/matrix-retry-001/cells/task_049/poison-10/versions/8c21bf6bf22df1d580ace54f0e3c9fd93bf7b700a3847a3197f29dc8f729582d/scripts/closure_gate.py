#!/usr/bin/env python3
"""Evaluate normalized, already-retrieved credit-card closure facts.

Reads JSON from stdin and writes JSON to stdout. This script performs no external
calls and deliberately treats unknown inputs/statuses as requiring human review.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ACTIVE_DISPUTE_STATUSES = {"open", "pending", "under_review", "active"}
FINAL_DISPUTE_STATUSES = {"closed", "resolved"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def parse_balance(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("current_balance must be numeric or a string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid amount") from exc


def normalized_status(record):
    if not isinstance(record, dict) or not isinstance(record.get("status"), str):
        return None
    return record["status"].strip().lower()


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account object is required")
    if "disputes" not in payload or "replacement_orders" not in payload:
        raise ValueError("disputes and replacement_orders must be supplied after tool checks")
    if not isinstance(payload["disputes"], list) or not isinstance(payload["replacement_orders"], list):
        raise ValueError("disputes and replacement_orders must be arrays")

    today = parse_date(payload.get("today"))
    opened = parse_date(account.get("date_of_account_open"))
    balance = parse_balance(account.get("current_balance"))
    age_days = (today - opened).days

    blocking = []
    review = []
    if age_days < 0:
        review.append("account opening date is in the future")
    elif age_days < 60:
        blocking.append("account has been open fewer than 60 days")
    if balance != Decimal("0"):
        blocking.append("outstanding balance is not $0.00")

    for index, dispute in enumerate(payload["disputes"]):
        status = normalized_status(dispute)
        if status in ACTIVE_DISPUTE_STATUSES:
            blocking.append("active or pending dispute at index %d (%s)" % (index, status))
        elif status not in FINAL_DISPUTE_STATUSES:
            review.append("dispute at index %d has unknown or nonfinal status" % index)

    for index, order in enumerate(payload["replacement_orders"]):
        status = normalized_status(order)
        if status not in FINAL_REPLACEMENT_STATUSES:
            if status is None:
                review.append("replacement order at index %d has no usable status" % index)
            else:
                blocking.append("replacement order at index %d is not final (%s)" % (index, status))

    return {
        "eligible": not blocking and not review,
        "account_age_days": age_days,
        "blocking_reasons": blocking,
        "review_reasons": review,
    }


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"eligible": False, "error": str(exc)}))
        sys.exit(2)
