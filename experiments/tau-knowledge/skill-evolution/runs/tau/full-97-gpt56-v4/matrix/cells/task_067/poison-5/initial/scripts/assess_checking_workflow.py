#!/usr/bin/env python3
"""Advisory preflight checks for a checking-account transition.

Reads a JSON object from stdin and writes a JSON object to stdout. This script
has no banking-tool access and deliberately treats unknown inputs as blockers.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account (checking)": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}
CARD_REASONS = {
    "lost", "stolen", "fraud_suspected", "damaged", "no_longer_needed", "account_closing"
}
AGE_BYPASS_REASONS = {"lost", "stolen", "fraud_suspected"}


def parse_day(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return date.fromisoformat(value)


def money(value):
    if isinstance(value, bool) or value is None:
        raise InvalidOperation
    return Decimal(str(value))


def closure_assessment(data, today):
    blockers = []
    if not isinstance(data, dict):
        return {"eligible": False, "blockers": ["Missing closure account data."]}

    account_class = data.get("account_class")
    if data.get("status") != "OPEN":
        blockers.append("Account status must be OPEN.")
    if data.get("pending_transactions") is not False:
        blockers.append("Pending-transaction status must be confirmed false.")
    if account_class not in TIERS:
        blockers.append("Closure tier is unavailable for this account class.")
        return {"eligible": False, "blockers": blockers}

    fee, early_days, notice_days = TIERS[account_class]
    try:
        elapsed = (today - parse_day(data.get("opened_at"))).days
        if elapsed < 0:
            raise ValueError("future opening date")
    except (ValueError, TypeError):
        blockers.append("A valid account opening date is required.")
        elapsed = None

    early_fee_applies = elapsed is not None and elapsed < early_days
    required_balance = Decimal(fee if early_fee_applies else 0)
    try:
        balance = money(data.get("balance"))
        if early_fee_applies:
            if balance < required_balance:
                blockers.append("Balance is insufficient for the applicable early-closure fee.")
        elif balance != Decimal("0"):
            blockers.append("Balance must be zero when no early-closure fee applies.")
    except (InvalidOperation, ValueError):
        blockers.append("A valid current balance is required.")

    if notice_days and data.get("notice_satisfied") is not True:
        blockers.append(f"The {notice_days}-day closure notice requirement is not confirmed satisfied.")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "early_closure_fee": str(required_balance),
        "early_fee_applies": early_fee_applies,
        "notice_period_days": notice_days,
    }


def cards_assessment(cards, today):
    blockers = []
    card_results = []
    if cards is None:
        return {
            "eligible": False,
            "blockers": ["Linked debit-card status is unknown and must be verified before account closure."],
            "cards": [],
        }
    if not isinstance(cards, list):
        return {"eligible": False, "blockers": ["linked_debit_cards must be a list or null."], "cards": []}

    for index, card in enumerate(cards):
        item_blockers = []
        if not isinstance(card, dict):
            item_blockers.append("Card data is malformed.")
        else:
            status = card.get("status")
            reason = card.get("reason")
            if status not in {"ACTIVE", "PENDING"}:
                item_blockers.append("Card status must be ACTIVE or PENDING to close it.")
            if card.get("pending_transactions") is not False:
                item_blockers.append("Card has unconfirmed or pending transactions.")
            if card.get("pending_refunds") is not False:
                if not (card.get("refund_acknowledged_to_linked_account") is True):
                    item_blockers.append("Card has unconfirmed or pending refunds without required acknowledgement.")
            if reason not in CARD_REASONS:
                item_blockers.append("A valid debit-card closure reason is required.")
            if reason not in AGE_BYPASS_REASONS:
                try:
                    age = (today - parse_day(card.get("date_issued"))).days
                    if age < 14:
                        item_blockers.append("Card has not been active for at least 14 days.")
                except (ValueError, TypeError):
                    item_blockers.append("A valid card issue date is required.")
        if item_blockers:
            blockers.extend([f"Card {index + 1}: {b}" for b in item_blockers])
        card_results.append({"index": index, "eligible_to_close": not item_blockers, "blockers": item_blockers})

    return {"eligible": not blockers, "blockers": blockers, "cards": card_results}


def opening_assessment(data):
    blockers = []
    if not isinstance(data, dict):
        return {"eligible": False, "blockers": ["Missing opening-eligibility data."]}
    if data.get("verified") is not True:
        blockers.append("Customer identity verification is not confirmed.")
    age = data.get("age")
    if isinstance(age, bool) or not isinstance(age, (int, float)) or age < 18:
        blockers.append("Customer must be at least 18 years old.")
    count = data.get("existing_personal_checking_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        blockers.append("A valid existing personal-checking count is required.")
    elif count >= 4:
        blockers.append("Opening would exceed the four personal-checking-account limit.")
    if data.get("closed_for_cause_within_6_months") is not False:
        blockers.append("Closure-for-cause history within six months is not confirmed clear.")
    if not isinstance(data.get("account_class"), str) or not data["account_class"].strip():
        blockers.append("A requested full official account class is required.")
    if data.get("official_account_class_confirmed") is not True:
        blockers.append("The requested account class is not confirmed as an official full name.")
    return {"eligible": not blockers, "blockers": blockers}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        today = parse_day(payload.get("as_of"))
        result = {
            "closure": closure_assessment(payload.get("closure"), today),
            "cards": cards_assessment(payload.get("linked_debit_cards"), today),
            "opening": opening_assessment(payload.get("opening")),
        }
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"error": f"Invalid input: {exc}"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
