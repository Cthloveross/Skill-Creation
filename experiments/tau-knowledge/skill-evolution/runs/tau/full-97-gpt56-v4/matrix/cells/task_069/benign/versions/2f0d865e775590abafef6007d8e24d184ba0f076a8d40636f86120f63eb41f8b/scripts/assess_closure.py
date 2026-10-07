#!/usr/bin/env python3
"""Assess documented checking-account closure prerequisites.

Input (JSON object on stdin):
  account_class: official class string
  status: account status
  balance: numeric USD value or string
  date_opened: ISO YYYY-MM-DD date (or datetime beginning with that date)
  as_of: ISO YYYY-MM-DD date (or datetime beginning with that date)
  transactions: optional list of objects with a status field

Output (JSON object): fee/notice details, parsed age, blockers, and
eligible_to_close. This script recommends no bank action.
"""
import json
import sys
from datetime import date
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


def parse_date(value, field, blockers):
    if not isinstance(value, str) or len(value) < 10:
        blockers.append(f"missing_or_invalid_{field}")
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        blockers.append(f"missing_or_invalid_{field}")
        return None


def parse_money(value, blockers):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise InvalidOperation
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        blockers.append("missing_or_invalid_balance")
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    blockers = []
    account_class = data.get("account_class")
    tier = TIERS.get(account_class)
    if tier is None:
        blockers.append("unsupported_or_unknown_account_class")
        window_days = fee = notice_days = None
    else:
        window_days, fee, notice_days = tier

    if data.get("status") != "OPEN":
        blockers.append("account_status_must_be_OPEN")

    transactions = data.get("transactions")
    if not isinstance(transactions, list):
        blockers.append("transaction_history_missing_or_invalid")
        pending_count = None
    else:
        pending_count = sum(
            1 for transaction in transactions
            if isinstance(transaction, dict)
            and str(transaction.get("status", "")).lower() == "pending"
        )
        if pending_count:
            blockers.append("pending_transactions_present")

    balance = parse_money(data.get("balance"), blockers)
    opened = parse_date(data.get("date_opened"), "date_opened", blockers)
    as_of = parse_date(data.get("as_of"), "as_of", blockers)
    account_age_days = None
    early_fee_applies = None

    if opened is not None and as_of is not None:
        account_age_days = (as_of - opened).days
        if account_age_days < 0:
            blockers.append("as_of_precedes_date_opened")
        elif tier is not None:
            early_fee_applies = account_age_days < window_days

    if balance is not None and early_fee_applies is not None and fee is not None:
        if early_fee_applies:
            if balance < fee:
                blockers.append("insufficient_balance_for_early_closure_fee")
        elif balance != Decimal("0.00"):
            blockers.append("balance_must_be_zero_when_no_early_fee")

    output = {
        "account_class": account_class,
        "account_age_days": account_age_days,
        "early_fee_window_days": window_days,
        "early_closure_fee": str(fee) if fee is not None else None,
        "early_fee_applies": early_fee_applies,
        "notice_period_days": notice_days,
        "balance": str(balance) if balance is not None else None,
        "pending_transaction_count": pending_count,
        "blockers": blockers,
        "eligible_to_close": not blockers,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
