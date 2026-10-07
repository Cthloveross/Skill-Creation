#!/usr/bin/env python3
"""Assess credit-card closure prerequisites from verified runtime facts.

Input: one JSON object on stdin. Output: one JSON object on stdout.
This program performs no banking action.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
ACTIVE_DISPUTE_STATUSES = {
    "open", "pending", "active", "under_review", "under review",
    "in_progress", "in progress",
}
RESOLVED_DISPUTE_STATUSES = {"closed", "resolved", "dismissed", "withdrawn"}


def parse_date(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string or null")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("outstanding_balance must be a number, dollar string, or null")
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("outstanding_balance is not a valid monetary value")
    if not amount.is_finite():
        raise ValueError("outstanding_balance must be finite")
    return amount


def parse_statuses(value, field):
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{field} must be an array of strings or null")
    return [x.strip().lower() for x in value]


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    current = parse_date(payload.get("current_date"), "current_date")
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    balance = parse_money(payload.get("outstanding_balance"))
    disputes = parse_statuses(payload.get("dispute_statuses"), "dispute_statuses")
    replacements = parse_statuses(
        payload.get("replacement_order_statuses"), "replacement_order_statuses"
    )

    blockers = []
    needs_verification = []
    age_days = None

    if current is None:
        needs_verification.append("current_date")
    if opened is None:
        needs_verification.append("account_open_date")
    if current is not None and opened is not None:
        age_days = (current - opened).days
        if age_days < 0:
            blockers.append("account opening date is in the future")
        elif age_days < 60:
            blockers.append("account has been open fewer than 60 days")

    if balance is None:
        needs_verification.append("outstanding_balance")
    elif balance != Decimal("0"):
        blockers.append("outstanding balance is not $0.00")

    if disputes is None:
        needs_verification.append("dispute_statuses")
    else:
        unknown_dispute_statuses = sorted(
            {status for status in disputes if status not in ACTIVE_DISPUTE_STATUSES
             and status not in RESOLVED_DISPUTE_STATUSES}
        )
        if any(status in ACTIVE_DISPUTE_STATUSES for status in disputes):
            blockers.append("active or pending dispute exists")
        if unknown_dispute_statuses:
            needs_verification.append(
                "unrecognized dispute status: " + ", ".join(unknown_dispute_statuses)
            )

    if replacements is None:
        needs_verification.append("replacement_order_statuses")
    else:
        blank_status = any(not status for status in replacements)
        nonfinal = [status for status in replacements if status not in FINAL_REPLACEMENT_STATUSES]
        if nonfinal:
            blockers.append("pending or non-final replacement-card order exists")
        if blank_status:
            needs_verification.append("replacement order with missing status")

    return {
        "account_age_days": age_days,
        "closure_eligible": not blockers and not needs_verification,
        "blockers": blockers,
        "needs_verification": needs_verification,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(assess(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
