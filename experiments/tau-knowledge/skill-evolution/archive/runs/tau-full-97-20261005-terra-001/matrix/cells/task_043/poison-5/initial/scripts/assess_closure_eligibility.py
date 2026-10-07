#!/usr/bin/env python3
"""Assess credit-card closure prerequisites from a collected JSON snapshot.

Input JSON schema:
{
  "as_of": "YYYY-MM-DD",
  "date_opened": "YYYY-MM-DD",
  "current_balance": "75.00",
  "disputes": [{"status": "closed"}],
  "replacement_orders": [{"status": "delivered"}]
}

Output JSON contains an eligibility boolean, blockers, invalid fields, and facts.
This script is deliberately read-only: it neither calls banking tools nor initiates closure.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "cancelled", "canceled"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value: Any, field: str, invalid: list[str]) -> date | None:
    if not isinstance(value, str):
        invalid.append(field)
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        invalid.append(field)
        return None


def parse_balance(value: Any, invalid: list[str]) -> Decimal | None:
    if not isinstance(value, (str, int, float)):
        invalid.append("current_balance")
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        invalid.append("current_balance")
        return None


def status_of(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    value = record.get("status")
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print(json.dumps({
            "eligible": False,
            "blockers": [],
            "invalid_fields": ["input_json"],
            "facts": {},
        }))
        return

    if not isinstance(payload, dict):
        print(json.dumps({
            "eligible": False,
            "blockers": [],
            "invalid_fields": ["input_json"],
            "facts": {},
        }))
        return

    invalid: list[str] = []
    as_of = parse_date(payload.get("as_of"), "as_of", invalid)
    opened = parse_date(payload.get("date_opened"), "date_opened", invalid)
    balance = parse_balance(payload.get("current_balance"), invalid)

    disputes = payload.get("disputes")
    if not isinstance(disputes, list):
        invalid.append("disputes")
        disputes = []

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        invalid.append("replacement_orders")
        orders = []

    blockers: list[str] = []
    facts: dict[str, Any] = {
        "balance": str(balance) if balance is not None else None,
        "account_age_days": None,
        "unresolved_dispute_count": None,
        "nonfinal_replacement_order_count": None,
    }

    if as_of is not None and opened is not None:
        age_days = (as_of - opened).days
        facts["account_age_days"] = age_days
        if age_days < 0:
            invalid.append("date_opened_after_as_of")
        elif age_days < 60:
            blockers.append("account_age_under_60_days")

    if balance is not None and balance != Decimal("0"):
        blockers.append("outstanding_balance_not_zero")

    unresolved_disputes = 0
    for dispute in disputes:
        status = status_of(dispute)
        # A record with no reliably final status cannot be treated as resolved.
        if status not in FINAL_DISPUTE_STATUSES:
            unresolved_disputes += 1
    facts["unresolved_dispute_count"] = unresolved_disputes
    if unresolved_disputes:
        blockers.append("active_or_unresolved_dispute")

    nonfinal_orders = 0
    for order in orders:
        status = status_of(order)
        # Replacement policy permits closure only if every order is final.
        if status not in FINAL_REPLACEMENT_STATUSES:
            nonfinal_orders += 1
    facts["nonfinal_replacement_order_count"] = nonfinal_orders
    if nonfinal_orders:
        blockers.append("pending_replacement_card_order")

    result = {
        "eligible": not invalid and not blockers,
        "blockers": blockers,
        "invalid_fields": invalid,
        "facts": facts,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
