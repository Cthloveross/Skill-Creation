#!/usr/bin/env python3
"""Deterministically assess documented personal-checking closure prerequisites.

Reads a JSON object from stdin and writes a JSON object to stdout.  This helper
is advisory only and deliberately has no bank-tool or filesystem side effects.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("ENTRY", 30, Decimal("15.00"), 0),
    "Light Green Account": ("ENTRY", 30, Decimal("15.00"), 0),
    "Green Fee-Free Account": ("ENTRY", 30, Decimal("15.00"), 0),
    "Blue Account": ("MID", 60, Decimal("25.00"), 3),
    "Green Account (checking)": ("MID", 60, Decimal("25.00"), 3),
    "Evergreen Account": ("PREMIUM", 90, Decimal("50.00"), 7),
    "Bluest Account": ("ELITE", 180, Decimal("100.00"), 14),
}


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(1)


def parse_date(value, field):
    if not isinstance(value, str):
        fail(f"{field} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    fail(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    required = ("account_class", "date_opened", "as_of", "status", "balance", "transactions")
    missing = [key for key in required if key not in data]
    if missing:
        fail("missing required field(s): " + ", ".join(missing))

    account_class = data["account_class"]
    if account_class not in TIERS:
        print(json.dumps({
            "ok": True,
            "recognized_account_class": False,
            "account_class": account_class,
            "can_close": False,
            "blocking_conditions": ["Unsupported account class; determine its documented closure terms before proceeding."],
        }, sort_keys=True))
        return

    opened = parse_date(data["date_opened"], "date_opened")
    as_of = parse_date(data["as_of"], "as_of")
    if opened > as_of:
        fail("date_opened cannot be after as_of")
    try:
        balance = Decimal(str(data["balance"]))
    except (InvalidOperation, ValueError):
        fail("balance must be a decimal amount")
    if not balance.is_finite():
        fail("balance must be finite")
    transactions = data["transactions"]
    if not isinstance(transactions, list):
        fail("transactions must be a list")

    tier, window_days, early_fee, notice_days = TIERS[account_class]
    age_days = (as_of - opened).days
    fee_applies = age_days <= window_days
    applicable_fee = early_fee if fee_applies else Decimal("0.00")
    pending_count = sum(
        1 for tx in transactions
        if isinstance(tx, dict) and str(tx.get("status", "")).lower() == "pending"
    )

    notice_elapsed = data.get("notice_days_elapsed")
    if notice_elapsed is None:
        notice_satisfied = notice_days == 0
        notice_state = "not_required" if notice_days == 0 else "unknown"
    elif isinstance(notice_elapsed, int) and notice_elapsed >= 0:
        notice_satisfied = notice_elapsed >= notice_days
        notice_state = "satisfied" if notice_satisfied else "not_yet_satisfied"
    else:
        fail("notice_days_elapsed must be a non-negative integer when supplied")

    status_open = str(data["status"]).upper() == "OPEN"
    balance_sufficient = balance >= applicable_fee if fee_applies else balance == Decimal("0")
    blockers = []
    if not status_open:
        blockers.append("Account status must be OPEN.")
    if pending_count:
        blockers.append(f"{pending_count} pending transaction(s) must clear.")
    if not balance_sufficient:
        if fee_applies:
            blockers.append("Balance is below the applicable early-closure fee.")
        else:
            blockers.append("Balance must be exactly zero when no early-closure fee applies.")
    if not notice_satisfied:
        if notice_state == "unknown":
            blockers.append("Notice-period timing is not established.")
        else:
            blockers.append("Required notice period has not elapsed.")

    result = {
        "ok": True,
        "recognized_account_class": True,
        "tier": tier,
        "account_age_days": age_days,
        "early_closure_window_days": window_days,
        "fee_applies": fee_applies,
        "applicable_early_closure_fee": format(applicable_fee, ".2f"),
        "notice_period_days": notice_days,
        "notice_state": notice_state,
        "status_open": status_open,
        "pending_transaction_count": pending_count,
        "balance": format(balance, ".2f"),
        "balance_requirement_satisfied": balance_sufficient,
        "can_close": not blockers,
        "blocking_conditions": blockers,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
