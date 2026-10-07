#!/usr/bin/env python3
"""Evaluate documented checking-account closure prerequisites.

Input: one JSON object on stdin. Output: one JSON object on stdout.
This utility does not call banking tools and does not execute a closure.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

TIERS: Dict[str, Tuple[str, int, Decimal, int]] = {
    "Light Blue Account": ("entry", 30, Decimal("15.00"), 0),
    "Light Green Account": ("entry", 30, Decimal("15.00"), 0),
    "Green Fee-Free Account": ("entry", 30, Decimal("15.00"), 0),
    "Blue Account": ("mid", 60, Decimal("25.00"), 3),
    "Green Account (checking)": ("mid", 60, Decimal("25.00"), 3),
    "Evergreen Account": ("premium", 90, Decimal("50.00"), 7),
    "Bluest Account": ("elite", 180, Decimal("100.00"), 14),
}


def parse_date(value: Any) -> Optional[date]:
    """Parse a documented account date or a current-time value to a date."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    candidates = ["%m/%d/%Y", "%Y-%m-%d"]
    # Bank time output begins with an ISO calendar date followed by time and zone.
    if len(text) >= 10:
        candidates.append("%Y-%m-%d %H:%M:%S")
    for fmt in candidates:
        try:
            if fmt == "%Y-%m-%d %H:%M:%S":
                return datetime.strptime(text[:19], fmt).date()
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_money(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "")
    # Parenthesized amounts are conventional negative currency notation.
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def pending_from_input(data: Dict[str, Any]) -> Tuple[Optional[bool], Optional[str]]:
    if "transactions" in data:
        transactions = data["transactions"]
        if not isinstance(transactions, list):
            return None, "transactions must be a list when supplied"
        for item in transactions:
            if not isinstance(item, dict) or not isinstance(item.get("status"), str):
                return None, "each transaction must include a string status"
        return any(item["status"].strip().lower() == "pending" for item in transactions), None
    if "pending_transactions" in data:
        value = data["pending_transactions"]
        if isinstance(value, bool):
            return value, None
        return None, "pending_transactions must be boolean when supplied"
    return None, "pending transaction status is missing"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible_to_submit": False, "blockers": ["invalid JSON input: " + str(exc)]}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"eligible_to_submit": False, "blockers": ["input must be a JSON object"]}))
        return

    blockers: List[str] = []
    account_class = data.get("account_class")
    if not isinstance(account_class, str) or account_class not in TIERS:
        blockers.append("unsupported or missing account_class; do not infer a tier")
        tier = window_days = fee = notice_days = None
    else:
        tier, window_days, fee, notice_days = TIERS[account_class]

    opened = parse_date(data.get("date_opened"))
    today = parse_date(data.get("current_time"))
    age_days: Optional[int] = None
    early: Optional[bool] = None
    if opened is None:
        blockers.append("missing or invalid date_opened")
    if today is None:
        blockers.append("missing or invalid current_time")
    if opened is not None and today is not None:
        age_days = (today - opened).days
        if age_days < 0:
            blockers.append("date_opened is after current_time")
        elif window_days is not None:
            # "Within N days" includes the Nth calendar day.
            early = age_days <= window_days

    status = data.get("status")
    if not isinstance(status, str) or not status.strip():
        blockers.append("missing account status")
    elif status.strip().upper() != "OPEN":
        blockers.append("account status is not OPEN")

    pending, pending_error = pending_from_input(data)
    if pending_error:
        blockers.append(pending_error)
    elif pending:
        blockers.append("account has pending transactions")

    balance = parse_money(data.get("balance"))
    if balance is None:
        blockers.append("missing or invalid balance")

    effective_fee: Optional[Decimal] = None
    required_balance: Optional[Decimal] = None
    if fee is not None and early is not None:
        effective_fee = fee if early else Decimal("0.00")
        required_balance = effective_fee
        if balance is not None:
            if early and balance < effective_fee:
                blockers.append("balance is insufficient for the applicable early-closure fee")
            elif not early and balance != Decimal("0.00"):
                blockers.append("balance must be exactly $0.00 when no early-closure fee applies")

    result: Dict[str, Any] = {
        "eligible_to_submit": not blockers,
        "account_class": account_class if isinstance(account_class, str) else None,
        "tier": tier,
        "age_days": age_days,
        "early_closure_fee_applies": early,
        "fee_usd": str(effective_fee) if effective_fee is not None else None,
        "notice_days": notice_days,
        "required_minimum_balance_usd": str(required_balance) if required_balance is not None else None,
        "pending_transactions": pending,
        "blockers": blockers,
        "requirements": {
            "status": "OPEN",
            "pending_transactions": False,
            "balance_rule": "balance >= applicable fee when early; otherwise balance must equal 0.00",
            "confirmation_needed": True,
        },
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
