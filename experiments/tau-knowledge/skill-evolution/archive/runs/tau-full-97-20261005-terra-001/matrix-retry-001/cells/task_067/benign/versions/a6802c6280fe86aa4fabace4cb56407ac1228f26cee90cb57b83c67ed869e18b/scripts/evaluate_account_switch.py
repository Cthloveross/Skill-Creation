#!/usr/bin/env python3
"""Side-effect-free evaluator for a normalized checking-account switch case.

Reads a JSON object from stdin and writes a JSON object to stdout. It never calls
banking tools and does not replace the executor's required tool retrievals.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": (Decimal("15"), 30, 0),
    "Light Green Account": (Decimal("15"), 30, 0),
    "Green Fee-Free Account": (Decimal("15"), 30, 0),
    "Blue Account": (Decimal("25"), 60, 3),
    "Green Account (checking)": (Decimal("25"), 60, 3),
    "Evergreen Account": (Decimal("50"), 90, 7),
    "Bluest Account": (Decimal("100"), 180, 14),
}


def as_date(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        return None


def normalized_status(value):
    return str(value or "").strip().lower()


def main(case):
    blockers = []
    now = as_date(case.get("current_time"))
    user = case.get("user") or {}
    old = case.get("old_account") or {}
    transactions = case.get("transactions")
    cards = case.get("cards")
    opening = case.get("opening") or {}

    if now is None:
        return {"error": "current_time must be a parseable date or timestamp"}
    if not isinstance(transactions, list):
        blockers.append("Transaction history was not retrieved.")
        transactions = []
    if not isinstance(cards, list):
        blockers.append("Linked debit-card records were not retrieved.")
        cards = []

    verified = user.get("verified") is True
    if not verified:
        blockers.append("Customer identity is not verified.")
    if not old.get("account_id"):
        blockers.append("No old account is selected.")
    if normalized_status(old.get("status")) != "open":
        blockers.append("Old account must be OPEN.")

    tier = TIERS.get(old.get("account_class"))
    opened = as_date(old.get("date_opened"))
    balance = money(old.get("current_holdings", old.get("balance")))
    fee = None
    notice_days = None
    if tier is None:
        blockers.append("Old account class has no documented closure tier.")
    elif opened is None:
        blockers.append("Old account opening date is unavailable.")
    else:
        base_fee, window, notice_days = tier
        age = (now - opened).days
        if age < 0:
            blockers.append("Old account opening date is in the future.")
        else:
            fee = base_fee if age < window else Decimal("0")
            if notice_days and case.get("notice_completed") is not True:
                blockers.append("Required account-closure notice is not established.")
    if fee is None or balance is None:
        blockers.append("Old account balance requirement cannot be evaluated.")
    elif fee == 0 and balance != 0:
        blockers.append("Old account balance must be zero when no early-closure fee applies.")
    elif fee > 0 and balance < fee:
        blockers.append("Old account balance does not cover its early-closure fee.")

    pending = [t for t in transactions if normalized_status((t or {}).get("status")) in {"pending", "processing"}]
    if pending:
        blockers.append("Old account has pending or processing transactions.")

    eligible_cards = []
    for card in cards:
        card = card or {}
        if normalized_status(card.get("status")) == "closed":
            continue
        card_id = card.get("card_id")
        card_blocked = False
        if not card_id:
            card_blocked = True
        if card.get("user_id") != user.get("user_id"):
            card_blocked = True
        if normalized_status(card.get("status")) not in {"active", "pending"}:
            card_blocked = True
        issued = as_date(card.get("date_issued"))
        if issued is None or (now - issued).days < 14:
            card_blocked = True
        if case.get("card_closure_authorized") is not True:
            card_blocked = True
        if pending:
            card_blocked = True
        if card_blocked:
            blockers.append("Linked debit card %s is not eligible for account-closing closure." % (card_id or "(unknown)"))
        else:
            eligible_cards.append(card_id)

    dob = as_date(user.get("date_of_birth"))
    if dob is None:
        blockers.append("Customer age is unavailable for replacement opening.")
    else:
        age = now.year - dob.year - ((now.month, now.day) < (dob.month, dob.day))
        if age < 18:
            blockers.append("Customer must be at least 18 to open personal checking.")
    requested = opening.get("requested_account_class")
    if not isinstance(requested, str) or not requested.strip().endswith("Account"):
        blockers.append("Replacement class must be the confirmed full official Account name.")
    count = opening.get("open_personal_checking_count_after_old_close")
    try:
        count = int(count)
    except (TypeError, ValueError):
        blockers.append("Reconciled open personal-checking count is unavailable.")
        count = None
    if count is not None and count + 1 > 4:
        blockers.append("Replacement would exceed four personal checking accounts.")
    if opening.get("closed_for_cause_in_last_6_months") is not False:
        blockers.append("Recent checking-account closure-for-cause status is not cleared.")

    return {
        "old_account_eligible": not any("Old account" in b or "pending" in b.lower() or "notice" in b.lower() or "balance" in b.lower() or "tier" in b.lower() for b in blockers),
        "early_closure_fee": None if fee is None else format(fee, ".2f"),
        "notice_days": notice_days,
        "eligible_card_ids": eligible_cards,
        "switch_ready_for_execution": not blockers,
        "blockers": blockers,
        "next_actions": ([
            "Close every eligible linked debit card with reason account_closing.",
            "Close the old account after card closures succeed.",
            "Open the requested replacement only after old-account closure succeeds."
        ] if not blockers else ["Resolve blockers before performing dependent banking actions."])
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
