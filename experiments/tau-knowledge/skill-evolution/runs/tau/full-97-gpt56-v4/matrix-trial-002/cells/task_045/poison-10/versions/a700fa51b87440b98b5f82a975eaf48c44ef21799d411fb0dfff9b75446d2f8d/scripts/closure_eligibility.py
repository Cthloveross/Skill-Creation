#!/usr/bin/env python3
"""Evaluate supplied credit-card closure eligibility facts.

Input JSON:
  as_of: ISO-8601 datetime or date
  date_opened: ISO-8601 date or datetime
  current_balance: number or decimal string
  disputes: optional list of objects with a status field
  replacement_orders: optional list of objects with a status field
Output JSON:
  eligible, account_age_days, conditions, blockers

This helper is deliberately side-effect free. Callers must obtain and validate all
facts from normal banking tools and must repeat the replacement-order tool check
immediately before actual closure.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ACTIVE_DISPUTE_STATUSES = {"open", "pending", "under_review", "active", "in_progress"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date value must be a nonempty ISO-8601 string")
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("date value must be ISO-8601 date or datetime") from exc


def normalized_status(record):
    if not isinstance(record, dict) or not isinstance(record.get("status"), str):
        return None
    return record["status"].strip().lower().replace("-", "_").replace(" ", "_")


def main(payload):
    as_of = parse_date(payload.get("as_of"))
    opened = parse_date(payload.get("date_opened"))
    if opened > as_of:
        raise ValueError("date_opened cannot be after as_of")
    try:
        balance = Decimal(str(payload.get("current_balance")))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("current_balance must be numeric") from exc

    disputes = payload.get("disputes", [])
    orders = payload.get("replacement_orders", [])
    if not isinstance(disputes, list) or not isinstance(orders, list):
        raise ValueError("disputes and replacement_orders must be lists")

    age_days = (as_of - opened).days
    active_dispute = any(normalized_status(item) in ACTIVE_DISPUTE_STATUSES for item in disputes)
    nonfinal_order = any(normalized_status(item) not in FINAL_REPLACEMENT_STATUSES for item in orders)
    conditions = {
        "zero_balance": balance == Decimal("0"),
        "no_active_or_pending_disputes": not active_dispute,
        "account_age_at_least_60_days": age_days >= 60,
        "no_pending_replacement_cards": not nonfinal_order,
    }
    blockers = []
    if not conditions["zero_balance"]:
        blockers.append("outstanding_balance")
    if not conditions["no_active_or_pending_disputes"]:
        blockers.append("active_or_pending_dispute")
    if not conditions["account_age_at_least_60_days"]:
        blockers.append("account_under_60_days_old")
    if not conditions["no_pending_replacement_cards"]:
        blockers.append("pending_replacement_card")
    return {
        "eligible": not blockers,
        "account_age_days": age_days,
        "conditions": conditions,
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
