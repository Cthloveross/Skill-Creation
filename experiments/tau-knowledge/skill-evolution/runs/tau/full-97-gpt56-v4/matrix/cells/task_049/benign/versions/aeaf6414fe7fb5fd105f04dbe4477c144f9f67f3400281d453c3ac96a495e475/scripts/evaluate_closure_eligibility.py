#!/usr/bin/env python3
"""Evaluate credit-card closure prerequisites from JSON stdin.

Input object:
  current_date: YYYY-MM-DD or ISO-like timestamp (required)
  date_of_account_open: YYYY-MM-DD or ISO-like timestamp (required)
  current_balance: number or currency string such as "$0.00" (required)
  disputes: list of dispute objects (required; each may include status, card_last4,
            transaction.card_last4, or credit_card_account_id)
  replacement_orders: list of order objects (required; each may include status)

Output object contains eligible (bool), account_age_days (int or null), blockers
(list of machine-readable strings), and review_required (bool). This helper is
conservative for unknown statuses; a caller must associate user-level disputes to
the selected card before treating them as non-blocking.
"""
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError("date must begin with YYYY-MM-DD") from exc


def parse_balance(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("current_balance must be a number or string")
    normalized = re.sub(r"[^0-9.\-]", "", value)
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not numeric") from exc


def main(payload):
    required = ("current_date", "date_of_account_open", "current_balance", "disputes", "replacement_orders")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))
    if not isinstance(payload["disputes"], list) or not isinstance(payload["replacement_orders"], list):
        raise ValueError("disputes and replacement_orders must be arrays")

    today = parse_date(payload["current_date"])
    opened = parse_date(payload["date_of_account_open"])
    age_days = (today - opened).days
    blockers = []
    review_required = False

    if age_days < 60:
        blockers.append("account_under_60_days")
    if parse_balance(payload["current_balance"]) != Decimal("0"):
        blockers.append("nonzero_balance")

    unresolved_dispute_statuses = {"active", "open", "pending", "under_review", "in_review", "investigating"}
    final_dispute_statuses = {"closed", "resolved", "denied", "withdrawn", "cancelled", "canceled"}
    for dispute in payload["disputes"]:
        if not isinstance(dispute, dict):
            blockers.append("ambiguous_dispute_record")
            review_required = True
            continue
        status = str(dispute.get("status", "")).strip().lower()
        if status in unresolved_dispute_statuses:
            blockers.append("pending_or_active_dispute")
        elif status not in final_dispute_statuses:
            blockers.append("ambiguous_dispute_status")
            review_required = True

    final_order_statuses = {"delivered", "cancelled", "canceled"}
    for order in payload["replacement_orders"]:
        if not isinstance(order, dict):
            blockers.append("ambiguous_replacement_order")
            review_required = True
            continue
        status = str(order.get("status", "")).strip().lower()
        if status not in final_order_statuses:
            blockers.append("pending_or_ambiguous_replacement_order")
            if not status:
                review_required = True

    blockers = list(dict.fromkeys(blockers))
    return {
        "eligible": not blockers,
        "account_age_days": age_days,
        "blockers": blockers,
        "review_required": review_required,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"eligible": False, "error": str(error), "blockers": ["invalid_input"]}, sort_keys=True))
        sys.exit(2)
