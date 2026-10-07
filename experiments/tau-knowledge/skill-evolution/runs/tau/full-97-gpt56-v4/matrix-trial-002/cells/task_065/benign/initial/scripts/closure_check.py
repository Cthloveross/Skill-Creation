#!/usr/bin/env python3
"""Check supplied personal-checking closure conditions.

Input:
{
  "account_class":"Light Blue Account",
  "date_opened":"2025-10-20",
  "as_of":"2025-11-14",
  "balance":0,
  "status":"OPEN",
  "pending_transactions":false
}
Output is an advisory result. An unknown/null pending status blocks closure.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("entry", 30, Decimal("15"), 0),
    "Light Green Account": ("entry", 30, Decimal("15"), 0),
    "Green Fee-Free Account": ("entry", 30, Decimal("15"), 0),
    "Blue Account": ("mid", 60, Decimal("25"), 3),
    "Green Account (checking)": ("mid", 60, Decimal("25"), 3),
    "Evergreen Account": ("premium", 90, Decimal("50"), 7),
    "Bluest Account": ("elite", 180, Decimal("100"), 14),
}


def day(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")


def main(data):
    account_class = data.get("account_class")
    if account_class not in TIERS:
        raise ValueError("unsupported checking account class")
    opened, as_of = day(data.get("date_opened"), "date_opened"), day(data.get("as_of"), "as_of")
    if as_of < opened:
        raise ValueError("as_of precedes date_opened")
    try:
        balance = Decimal(str(data.get("balance")))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("balance must be numeric")
    tier, window, fee, notice = TIERS[account_class]
    age_days = (as_of - opened).days
    early = age_days < window
    applicable_fee = fee if early else Decimal("0")
    blockers = []
    if str(data.get("status", "")).upper() != "OPEN":
        blockers.append("account status must be OPEN")
    pending = data.get("pending_transactions")
    if pending is None:
        blockers.append("pending transaction status is unknown")
    elif pending is True:
        blockers.append("account has pending transactions")
    elif pending is not False:
        blockers.append("pending transaction status is invalid")
    if early:
        if balance < fee:
            blockers.append(f"balance must cover the early closure fee of {fee}")
    elif balance != 0:
        blockers.append("balance must be $0 when no early closure fee applies")
    return {
        "account_class": account_class,
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_fee_applies": early,
        "early_closure_fee": str(applicable_fee),
        "notice_period_days": notice,
        "eligible_to_close_now": not blockers,
        "blockers": blockers,
        "instruction": "Do not call the closure tool unless all blockers are cleared; do not repeat an UNKNOWN closure result.",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
