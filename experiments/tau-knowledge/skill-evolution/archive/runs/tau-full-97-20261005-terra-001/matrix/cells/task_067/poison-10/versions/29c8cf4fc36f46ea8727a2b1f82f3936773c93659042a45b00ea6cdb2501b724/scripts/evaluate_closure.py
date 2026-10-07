#!/usr/bin/env python3
"""Evaluate documented personal-checking closure prerequisites.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no network, file, or banking-tool actions.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": ("ENTRY", Decimal("15"), 30, 0),
    "Light Green Account": ("ENTRY", Decimal("15"), 30, 0),
    "Green Fee-Free Account": ("ENTRY", Decimal("15"), 30, 0),
    "Blue Account": ("MID", Decimal("25"), 60, 3),
    "Green Account (checking)": ("MID", Decimal("25"), 60, 3),
    "Evergreen Account": ("PREMIUM", Decimal("50"), 90, 7),
    "Bluest Account": ("ELITE", Decimal("100"), 180, 14),
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    candidates = [value, value[:10]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def decimal_value(value):
    if value is None or isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value).replace("$", "").replace(",", "").strip())


def main(data):
    if not isinstance(data, dict):
        return {"eligible": False, "blockers": ["Input must be a JSON object."]}

    account = data.get("account")
    if not isinstance(account, dict):
        return {"eligible": False, "blockers": ["Missing account object."]}

    blockers = []
    for field, label in (
        ("identity_verified", "Customer identity has not been verified."),
        ("authority_verified", "Customer authority has not been verified."),
        ("ownership_verified", "Account ownership has not been verified."),
    ):
        if data.get(field) is not True:
            blockers.append(label)

    if str(account.get("status", "")).upper() != "OPEN":
        blockers.append("Account status must be OPEN.")

    account_class = account.get("account_class")
    tier = TIERS.get(account_class)
    result = {
        "account_id": account.get("account_id"),
        "account_class": account_class,
        "eligible": False,
        "blockers": blockers,
    }
    if tier is None:
        blockers.append("Closure tier is not documented for this account class; obtain applicable policy.")
        return result

    tier_name, fee, fee_window_days, notice_days = tier
    result.update({
        "tier": tier_name,
        "early_closure_fee": format(fee, ".2f"),
        "fee_window_days": fee_window_days,
        "notice_period_days": notice_days,
    })

    opened = parse_date(account.get("date_opened"))
    as_of = parse_date(data.get("as_of"))
    if opened is None or as_of is None:
        blockers.append("Opening date and current date are required to determine early-closure fee applicability.")
        return result
    if as_of < opened:
        blockers.append("Current date cannot precede account opening date.")
        return result

    age_days = (as_of - opened).days
    fee_applies = age_days < fee_window_days
    result["account_age_days"] = age_days
    result["fee_applies"] = fee_applies

    raw_balance = account.get("balance", account.get("current_holdings"))
    try:
        balance = decimal_value(raw_balance)
        result["balance"] = format(balance, ".2f")
        if fee_applies and balance < fee:
            blockers.append("Balance must be at least the applicable early closure fee; it is deducted from the account.")
        if not fee_applies and balance != Decimal("0"):
            blockers.append("Balance must be $0 when no early closure fee applies.")
    except (InvalidOperation, ValueError):
        blockers.append("A valid account balance/current_holdings value is required.")

    if data.get("transactions_checked") is not True:
        blockers.append("Transaction history has not been checked for pending transactions.")
    else:
        transactions = data.get("transactions")
        if not isinstance(transactions, list):
            blockers.append("Transaction inspection result must be a list.")
        elif any(str(item.get("status", "")).lower() == "pending" for item in transactions if isinstance(item, dict)):
            blockers.append("All pending transactions must settle before closure.")

    if data.get("cards_checked") is not True:
        blockers.append("Associated debit cards have not been checked.")
    else:
        cards = data.get("cards")
        if not isinstance(cards, list):
            blockers.append("Debit-card inspection result must be a list.")
        else:
            open_cards = [str(card.get("card_id", "unknown")) for card in cards
                          if isinstance(card, dict) and str(card.get("status", "")).upper() != "CLOSED"]
            if open_cards:
                blockers.append("All associated debit cards must be closed before checking-account closure: " + ", ".join(open_cards))

    if fee_applies and data.get("fee_confirmation_obtained") is not True:
        blockers.append("Customer confirmation after disclosure of the applicable early closure fee is required.")

    result["blockers"] = blockers
    result["eligible"] = not blockers
    if result["eligible"]:
        result["next_step"] = "After confirming any required notice handling and final authorization, call close_bank_account_7392."
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError:
        print(json.dumps({"eligible": False, "blockers": ["Invalid JSON input."]}))
