#!/usr/bin/env python3
"""Check documented preconditions for directly closing a personal checking account.

Reads JSON from stdin and writes JSON to stdout. It is an advisory calculation only;
the caller must still obtain live account and transaction data and use banking tools.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": (30, Decimal("15.00"), 0),
    "Light Green Account": (30, Decimal("15.00"), 0),
    "Green Fee-Free Account": (30, Decimal("15.00"), 0),
    "Blue Account": (60, Decimal("25.00"), 3),
    "Green Account (checking)": (60, Decimal("25.00"), 3),
    "Evergreen Account": (90, Decimal("50.00"), 7),
    "Bluest Account": (180, Decimal("100.00"), 14),
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def main(payload):
    account = payload.get("account")
    transactions = payload.get("transactions")
    if not isinstance(account, dict):
        account = {}
    if not isinstance(transactions, list):
        transactions = None

    account_class = account.get("account_class")
    tier = TIERS.get(account_class)
    now = parse_date(payload.get("now"))
    opened = parse_date(account.get("date_opened"))
    balance = money(account.get("balance", account.get("current_holdings")))

    account_is_checking = str(account.get("account_type", "")).lower() == "checking"
    status_open = str(account.get("status", "")).upper() == "OPEN"
    supported_tier = tier is not None
    age_days = (now - opened).days if now and opened else None

    early = None
    fee = None
    notice_days = None
    if tier:
        window, tier_fee, notice_days = tier
        if age_days is not None:
            early = age_days < window
            fee = tier_fee if early else Decimal("0.00")

    no_pending = None
    if transactions is not None:
        no_pending = not any(
            isinstance(tx, dict) and str(tx.get("status", "")).lower() == "pending"
            for tx in transactions
        )

    balance_rule = None
    if balance is not None and early is not None and fee is not None:
        balance_rule = balance >= fee if early else balance == Decimal("0.00")

    checks = {
        "account_is_checking": account_is_checking,
        "account_status_is_OPEN": status_open,
        "supported_personal_checking_tier": supported_tier,
        "account_age_known": age_days is not None,
        "no_pending_transactions": no_pending,
        "balance_satisfies_closure_rule": balance_rule,
    }
    blockers = []
    labels = {
        "account_is_checking": "target account is not identified as checking",
        "account_status_is_OPEN": "account status must be OPEN",
        "supported_personal_checking_tier": "account class has no documented closure tier",
        "account_age_known": "account opening date or current date is unavailable",
        "no_pending_transactions": "pending transactions exist or transaction data is unavailable",
        "balance_satisfies_closure_rule": "balance does not satisfy the applicable fee/zero-balance rule or is unavailable",
    }
    for key, value in checks.items():
        if value is not True:
            blockers.append(labels[key])

    return {
        "valid": not blockers,
        "account_id": account.get("account_id"),
        "account_class": account_class,
        "age_days": age_days,
        "early_fee_applies": early,
        "fee": str(fee) if fee is not None else None,
        "notice_days": notice_days,
        "checks": checks,
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "valid": False}))
        sys.exit(2)
