#!/usr/bin/env python3
"""Evaluate supplied credit-card closure evidence.

Input JSON object:
  current_time: ISO-like timestamp beginning YYYY-MM-DD, or YYYY-MM-DD
  date_opened: MM/DD/YYYY or YYYY-MM-DD
  balance: number or currency string
  disputes: list of objects (optional). Each may contain status and matches_target
  replacement_orders: list of objects (optional). Each may contain status
  reward_points: integer/decimal optional

Output JSON has per-check results, blockers, account_age_days, and reward_cash_value.
This script does not call bank tools and does not initiate bank actions.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value):
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("expected MM/DD/YYYY or YYYY-MM-DD date")


def parse_money(value):
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned:
        raise ValueError("balance is missing or invalid")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("balance is missing or invalid") from exc


def main(data):
    now = parse_date(data["current_time"])
    opened = parse_date(data["date_opened"])
    age = (now - opened).days
    balance = parse_money(data["balance"])

    active_statuses = {"active", "open", "pending", "under_review", "under review"}
    disputes = data.get("disputes", [])
    dispute_block = any(
        isinstance(d, dict)
        and d.get("matches_target", True)
        and str(d.get("status", "")).strip().lower() in active_statuses
        for d in disputes
    )
    orders = data.get("replacement_orders", [])
    replacement_block = any(
        not isinstance(order, dict)
        or str(order.get("status", "")).strip().lower() not in {"delivered", "cancelled"}
        for order in orders
    )

    checks = {
        "zero_balance": balance == Decimal("0"),
        "no_pending_disputes": not dispute_block,
        "minimum_age_60_days": age >= 60,
        "no_pending_replacements": not replacement_block,
    }
    labels = {
        "zero_balance": "outstanding balance must be $0.00",
        "no_pending_disputes": "active or pending dispute blocks closure",
        "minimum_age_60_days": "account must be open at least 60 days",
        "no_pending_replacements": "pending replacement order blocks closure",
    }
    points = Decimal(str(data.get("reward_points", 0)))
    reward_value = (points * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "account_age_days": age,
        "checks": checks,
        "eligible_for_closure": all(checks.values()),
        "blockers": [labels[key] for key, passed in checks.items() if not passed],
        "reward_points": str(points),
        "reward_cash_value": f"${reward_value}",
        "note": "Advisory only; confirm data using required banking tools immediately before closure.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
