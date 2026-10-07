#!/usr/bin/env python3
"""Evaluate disclosed personal checking-account closure prerequisites.

Reads one JSON object from stdin and writes a JSON decision to stdout.  This
helper neither contacts banking systems nor causes any account action.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "light blue account": ("ENTRY", Decimal("15"), 30, 0),
    "light green account": ("ENTRY", Decimal("15"), 30, 0),
    "green fee-free account": ("ENTRY", Decimal("15"), 30, 0),
    "blue account": ("MID", Decimal("25"), 60, 3),
    "green account (checking)": ("MID", Decimal("25"), 60, 3),
    "evergreen account": ("PREMIUM", Decimal("50"), 90, 7),
    "bluest account": ("ELITE", Decimal("100"), 180, 14),
}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def parse_day(value, field, blockers):
    if not isinstance(value, str):
        blockers.append("invalid_" + field)
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        blockers.append("invalid_" + field)
        return None


def main(payload):
    blockers = []
    product = norm(payload.get("account_product"))
    tier_info = TIERS.get(product)
    if tier_info is None:
        blockers.append("unsupported_account_product")
        tier, fee, window, notice = None, None, None, None
    else:
        tier, fee, window, notice = tier_info

    if norm(payload.get("account_type")) not in {"checking", "checkings"}:
        blockers.append("not_a_checking_account")
    if norm(payload.get("status")) != "open":
        blockers.append("account_not_open")

    pending = payload.get("has_pending_transactions")
    if pending is not False:
        blockers.append("pending_transaction_status_not_clear" if pending is None else "pending_transactions_present")

    opened = parse_day(payload.get("date_opened"), "date_opened", blockers)
    processing = parse_day(payload.get("processing_date"), "processing_date", blockers)
    age_days = None
    in_window = None
    if opened and processing:
        age_days = (processing - opened).days
        if age_days < 0:
            blockers.append("date_opened_after_processing_date")
        elif tier_info is not None:
            in_window = age_days <= window

    balance = None
    try:
        balance = Decimal(str(payload.get("current_holdings")))
        if not balance.is_finite():
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        blockers.append("invalid_current_holdings")

    applicable_fee = Decimal("0")
    if tier_info is not None and in_window is True:
        applicable_fee = fee
        if balance is not None and balance < fee:
            blockers.append("insufficient_balance_for_early_closure_fee")
    elif tier_info is not None and in_window is False:
        if balance is not None and balance != Decimal("0"):
            blockers.append("nonzero_balance_without_early_fee")

    result = {
        "eligible": not blockers,
        "tier": tier,
        "early_closure_fee": format(applicable_fee, ".2f"),
        "notice_days": notice,
        "in_early_closure_window": in_window,
        "account_age_days": age_days,
        "blockers": blockers,
    }
    return result


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": False, "blockers": ["invalid_input"], "error": str(exc)}))
