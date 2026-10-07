#!/usr/bin/env python3
"""Assess documented personal-checking closure prerequisites from JSON stdin.

This script is intentionally read-only: it does not invoke banking tools and does
not replace live verification or post-action re-checks.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("entry", Decimal("15"), 30, 0),
    "Light Green Account": ("entry", Decimal("15"), 30, 0),
    "Green Fee-Free Account": ("entry", Decimal("15"), 30, 0),
    "Blue Account": ("mid", Decimal("25"), 60, 3),
    "Green Account (checking)": ("mid", Decimal("25"), 60, 3),
    "Evergreen Account": ("premium", Decimal("50"), 90, 7),
    "Bluest Account": ("elite", Decimal("100"), 180, 14),
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("unrecognized date format")


def as_decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid balance")
    if not result.is_finite():
        raise ValueError("invalid balance")
    return result


def main(payload):
    errors = []
    blockers = []
    account = payload.get("account")
    if not isinstance(account, dict):
        return {"input_errors": ["account must be an object"], "account_close_eligible_now": False}

    verified_user_id = payload.get("verified_user_id")
    if payload.get("identity_verified") is not True:
        blockers.append("Customer identity has not been verified and logged.")
    if not isinstance(verified_user_id, str) or not verified_user_id:
        blockers.append("A verified user ID is required for ownership checks.")
    elif account.get("user_id") != verified_user_id:
        blockers.append("Selected account does not match the verified customer.")
    if payload.get("target_account_confirmed") is not True:
        blockers.append("The exact account selected for closure has not been confirmed.")

    account_type = str(account.get("account_type", "")).lower()
    if account_type not in ("checking", "personal_checking", "personal checking"):
        blockers.append("Selected account is not identified as a personal checking account.")
    if str(account.get("status", "")).upper() != "OPEN":
        blockers.append("Account status must be OPEN.")

    account_class = account.get("account_class")
    tier_info = TIERS.get(account_class)
    result = {
        "input_errors": errors,
        "supported_account_class": tier_info is not None,
        "account_class": account_class,
        "account_close_eligible_now": False,
        "account_blockers": blockers,
        "card_close_candidates": [],
        "card_blockers": [],
        "all_linked_cards_closed": False,
    }
    if not tier_info:
        blockers.append("Unsupported or missing personal checking account class.")
        return result

    tier, fee, fee_window, notice_days = tier_info
    result.update({
        "tier": tier,
        "early_closure_fee": format(fee, ".2f"),
        "fee_window_days": fee_window,
        "notice_period_days": notice_days,
    })

    try:
        today = parse_date(payload.get("now"))
        opened = parse_date(account.get("date_opened"))
        days_open = (today - opened).days
        if days_open < 0:
            raise ValueError("date_opened is in the future")
        fee_applies = days_open <= fee_window
        result["days_open"] = days_open
        result["early_closure_fee_applies"] = fee_applies
    except ValueError as exc:
        errors.append("Cannot determine early-closure fee: %s." % exc)
        fee_applies = None
        result["early_closure_fee_applies"] = None

    try:
        balance = as_decimal(account.get("balance"))
        result["reported_balance"] = format(balance, ".2f")
        if fee_applies is True and balance < fee:
            blockers.append("Balance is less than the applicable early-closure fee.")
        elif fee_applies is False and balance != Decimal("0"):
            blockers.append("Balance must be exactly zero when no early-closure fee applies.")
    except ValueError as exc:
        errors.append("Cannot evaluate balance: %s." % exc)

    transactions = payload.get("transactions", [])
    if not isinstance(transactions, list):
        errors.append("transactions must be a list.")
    else:
        pending = [t for t in transactions if isinstance(t, dict) and str(t.get("status", "")).lower() == "pending"]
        result["pending_account_transaction_count"] = len(pending)
        if pending:
            blockers.append("Account has pending transactions.")

    cards = payload.get("cards", [])
    checks = payload.get("card_checks", {})
    if not isinstance(cards, list):
        errors.append("cards must be a list.")
        cards = []
    if not isinstance(checks, dict):
        errors.append("card_checks must be an object.")
        checks = {}

    all_closed = True
    for card in cards:
        if not isinstance(card, dict):
            errors.append("Each card must be an object.")
            all_closed = False
            continue
        card_id = card.get("card_id")
        status = str(card.get("status", "")).upper()
        label = str(card_id) if card_id else "an unidentified linked card"
        if status == "CLOSED":
            continue
        all_closed = False
        reasons = []
        if not card_id:
            reasons.append("missing card_id")
        if not isinstance(verified_user_id, str) or card.get("user_id") != verified_user_id:
            reasons.append("card ownership does not match the verified customer")
        if status not in ("ACTIVE", "PENDING"):
            reasons.append("card status must be ACTIVE or PENDING")
        check = checks.get(card_id) if card_id else None
        if not isinstance(check, dict):
            reasons.append("pending card transaction and refund checks are unavailable")
        else:
            if check.get("pending_transactions") is not False:
                reasons.append("card has pending/processing transactions or this check is not confirmed clear")
            if check.get("pending_refunds") is not False:
                reasons.append("card has pending refunds or this check is not confirmed clear")
        try:
            card_age = (today - parse_date(card.get("date_issued"))).days
            if card_age < 14:
                reasons.append("card is younger than 14 days")
        except (ValueError, UnboundLocalError):
            reasons.append("card issue date cannot establish the 14-day minimum age")
        if reasons:
            result["card_blockers"].append({"card_id": card_id, "reasons": reasons})
        else:
            result["card_close_candidates"].append({"card_id": card_id, "reason": "account_closing"})

    result["all_linked_cards_closed"] = all_closed
    if not all_closed:
        blockers.append("All linked debit cards must be confirmed CLOSED before account closure.")
    result["account_close_eligible_now"] = not errors and not blockers and all_closed
    return result


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(incoming), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"input_errors": [str(exc)], "account_close_eligible_now": False}))
