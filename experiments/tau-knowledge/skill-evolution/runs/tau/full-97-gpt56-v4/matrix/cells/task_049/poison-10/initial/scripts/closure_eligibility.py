#!/usr/bin/env python3
"""Deterministically assess documented credit-card closure prerequisites.

Reads one JSON object from stdin and writes a JSON assessment to stdout.
This helper does not call banking tools and is intentionally conservative.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}
FINAL_DISPUTE_STATUSES = {"closed", "resolved", "withdrawn", "denied", "won", "lost"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be MM/DD/YYYY or begin YYYY-MM-DD")


def parse_balance(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            pass
    raise ValueError("balance is not numeric")


def status_of(record):
    if not isinstance(record, dict) or not isinstance(record.get("status"), str):
        raise ValueError("record has no status")
    return record["status"].strip().lower()


def main(data):
    checks = {}
    blockers = []

    try:
        opened = parse_date(data.get("opened_on"))
        today = parse_date(data.get("current_date"))
        age_days = (today - opened).days
        checks["account_age"] = {"pass": age_days >= 60, "age_days": age_days}
        if age_days < 60:
            blockers.append("account is less than 60 days old")
    except (ValueError, TypeError) as exc:
        checks["account_age"] = {"pass": False, "error": str(exc)}
        blockers.append("account age could not be validated")

    try:
        balance = parse_balance(data.get("balance"))
        checks["zero_balance"] = {"pass": balance == Decimal("0"), "balance": str(balance)}
        if balance != Decimal("0"):
            blockers.append("outstanding balance is not zero")
    except (ValueError, TypeError) as exc:
        checks["zero_balance"] = {"pass": False, "error": str(exc)}
        blockers.append("balance could not be validated")

    disputes = data.get("disputes_for_account")
    if disputes is None:
        checks["no_pending_disputes"] = {"pass": False, "error": "account association unresolved"}
        blockers.append("dispute status for this account is unresolved")
    elif not isinstance(disputes, list):
        checks["no_pending_disputes"] = {"pass": False, "error": "must be a list or null"}
        blockers.append("dispute status could not be validated")
    else:
        try:
            active = [status_of(item) for item in disputes if status_of(item) not in FINAL_DISPUTE_STATUSES]
            checks["no_pending_disputes"] = {"pass": not active, "active_statuses": active}
            if active:
                blockers.append("active or pending dispute exists")
        except ValueError as exc:
            checks["no_pending_disputes"] = {"pass": False, "error": str(exc)}
            blockers.append("dispute status could not be validated")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        checks["no_pending_replacement"] = {"pass": False, "error": "must be a list"}
        blockers.append("replacement-order status could not be validated")
    else:
        try:
            nonfinal = [status_of(item) for item in orders if status_of(item) not in FINAL_ORDER_STATUSES]
            checks["no_pending_replacement"] = {"pass": not nonfinal, "nonfinal_statuses": nonfinal}
            if nonfinal:
                blockers.append("pending replacement card order exists")
        except ValueError as exc:
            checks["no_pending_replacement"] = {"pass": False, "error": str(exc)}
            blockers.append("replacement-order status could not be validated")

    return {"eligible": not blockers, "checks": checks, "blockers": blockers}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": False, "checks": {}, "blockers": ["invalid helper input"], "error": str(exc)}, sort_keys=True))
