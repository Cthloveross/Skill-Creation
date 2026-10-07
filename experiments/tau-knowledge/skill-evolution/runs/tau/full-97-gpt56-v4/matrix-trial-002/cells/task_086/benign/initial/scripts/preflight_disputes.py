#!/usr/bin/env python3
"""Deterministic debit-card dispute preflight helper.

Reads one JSON object from stdin and emits one JSON object to stdout. It makes no
bank calls and does not substitute for matching a live transaction or verifying a
customer. See SKILL.md for the input schema.
"""
import datetime as dt
import json
import sys

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
TIERS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
ELIGIBLE_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
NONFRAUD_CATEGORIES = CATEGORIES - {"card_present_fraud", "card_not_present_fraud"}


def date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} must be MM/DD/YYYY")
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError as exc:
        raise ValueError(f"{label} must be MM/DD/YYYY") from exc


def card_action(category):
    if category in {"card_present_fraud", "card_not_present_fraud"}:
        return "close_and_reissue"
    if category == "unauthorized_transaction":
        return "freeze_pending_investigation"
    return "keep_active"


def main(payload):
    as_of = date(payload.get("as_of"), "as_of")
    tier = payload.get("account_class")
    if tier not in TIERS:
        raise ValueError("account_class must be Entry, Mid, Premium, or Elite")
    existing = payload.get("open_disputes")
    if not isinstance(existing, int) or isinstance(existing, bool) or existing < 0:
        raise ValueError("open_disputes must be a non-negative integer")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("items must be an array")

    account_open = payload.get("account_open") is True
    restricted = payload.get("account_has_holds_or_restrictions") is True
    age = payload.get("account_age_days")
    if not isinstance(age, int) or isinstance(age, bool) or age < 0:
        raise ValueError("account_age_days must be a non-negative integer")

    results = []
    capacity = TIERS[tier]
    available = max(0, capacity - existing)
    projected_eligible = 0
    for index, item in enumerate(items):
        blockers = []
        category = item.get("category")
        tx_type = item.get("transaction_type")
        amount = item.get("amount")
        try:
            tx_date = date(item.get("transaction_date"), f"items[{index}].transaction_date")
            tx_age = (as_of - tx_date).days
        except ValueError as exc:
            tx_age = None
            blockers.append(str(exc))
        if category not in CATEGORIES:
            blockers.append("unsupported dispute category")
        if tx_type not in TRANSACTION_TYPES:
            blockers.append("unsupported transaction type")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
            blockers.append("disputed amount must be at least 1.00")
        if tx_age is not None and (tx_age < 0 or tx_age > 60):
            blockers.append("transaction is not within 60 days of filing")
        if not account_open:
            blockers.append("linked checking account is not OPEN")
        if category == "duplicate_charge" and item.get("is_first_duplicate") is not True:
            blockers.append("only the earliest duplicate transaction may be disputed")
        pin = item.get("pin_compromised")
        if pin not in PINS:
            blockers.append("pin_compromised must be yes_shared, yes_observed, no, or unknown")
        if not isinstance(item.get("written_statement_provided"), bool):
            blockers.append("written_statement_provided must be boolean")
        if not isinstance(item.get("timely_statement_report"), bool):
            blockers.append("timely_statement_report must be boolean")
        if not isinstance(item.get("contacted_merchant"), bool):
            blockers.append("contacted_merchant must be boolean")

        timely = item.get("timely_statement_report") is True
        written = item.get("written_statement_provided") is True
        contacted = item.get("contacted_merchant") is True
        provisional = (
            category in ELIGIBLE_CATEGORIES and timely and written and account_open
            and not restricted and pin != "yes_shared"
            and not (age < 30 and category == "card_not_present_fraud")
            and not (category in NONFRAUD_CATEGORIES and not contacted)
        )
        core_eligible = not blockers
        if core_eligible:
            projected_eligible += 1
        results.append({
            "index": index,
            "transaction_age_days": tx_age,
            "card_action": card_action(category) if category in CATEGORIES else None,
            "provisional_credit_eligible": provisional,
            "blockers": blockers,
        })

    overflow = max(0, projected_eligible - available)
    if overflow:
        # Capacity is consumed in input order, mirroring a deliberate filing order.
        seen = 0
        for result in results:
            if not result["blockers"]:
                seen += 1
                if seen > available:
                    result["blockers"].append("open-dispute limit would be exceeded for this account")

    return {
        "account_open_dispute_limit": capacity,
        "existing_open_disputes": existing,
        "available_slots_before_new_filings": available,
        "account_has_holds_or_restrictions": restricted,
        "items": results,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
