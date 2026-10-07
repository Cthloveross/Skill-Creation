#!/usr/bin/env python3
"""Validate supplied card inventory and create a non-executable security checklist.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
never verifies identity, contacts banking systems, or performs a banking action.
"""

import json
import sys
from typing import Any, Dict, List, Set


def records(value: Any, field: str, errors: List[str]) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    output: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            output.append(item)
        else:
            errors.append(f"{field}[{index}] must be an object")
    return output


def debit_view(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "card_id": card.get("card_id"),
        "account_id": card.get("account_id"),
        "last_4": card.get("card_number_last_4"),
        "status": card.get("status"),
    }


def credit_view(account: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "account_id": account.get("account_id"),
        "card_type": account.get("card_type"),
        "last_4": account.get("card_last_4_digits"),
        "account_status": account.get("account_status"),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"blocking_errors": [f"invalid JSON: {exc.msg}"]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"blocking_errors": ["input must be a JSON object"]}))
        return

    errors: List[str] = []
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        errors.append("user_id is required")
        user_id = ""
    if payload.get("identity_verified") is not True:
        errors.append("identity_verified must be true before any banking action")

    debit_cards = records(payload.get("debit_cards"), "debit_cards", errors)
    credit_accounts = records(payload.get("credit_accounts"), "credit_accounts", errors)

    selected_raw = payload.get("requested_debit_account_ids")
    selected_accounts: Set[str] = set()
    if selected_raw is not None:
        if not isinstance(selected_raw, list) or not all(
            isinstance(item, str) and item for item in selected_raw
        ):
            errors.append("requested_debit_account_ids must be an array of nonempty strings")
        else:
            selected_accounts = set(selected_raw)

    debit_candidates: List[Dict[str, Any]] = []
    debit_exclusions: List[Dict[str, Any]] = []
    seen_cards: Set[str] = set()
    returned_accounts: Set[str] = set()

    for card in debit_cards:
        card_id = card.get("card_id")
        account_id = card.get("account_id")
        reasons: List[str] = []
        if not isinstance(card_id, str) or not card_id:
            reasons.append("missing card_id")
        elif card_id in seen_cards:
            reasons.append("duplicate card_id")
        else:
            seen_cards.add(card_id)
        if selected_accounts and account_id not in selected_accounts:
            reasons.append("not in requested checking-account selection")
        elif isinstance(account_id, str):
            returned_accounts.add(account_id)
        if card.get("user_id") != user_id:
            reasons.append("card owner does not match verified user")
        if card.get("status") != "ACTIVE":
            reasons.append("card is not ACTIVE and cannot be temporarily frozen")

        if reasons:
            debit_exclusions.append({"card": debit_view(card), "reasons": reasons})
        else:
            debit_candidates.append(debit_view(card))

    if selected_accounts:
        missing = sorted(selected_accounts - returned_accounts)
        if missing:
            errors.append("no returned debit-card record for requested account IDs: " + ", ".join(missing))

    credit_offers: List[Dict[str, Any]] = []
    credit_exclusions: List[Dict[str, Any]] = []
    seen_credit_accounts: Set[str] = set()
    for account in credit_accounts:
        account_id = account.get("account_id")
        reasons: List[str] = []
        if not isinstance(account_id, str) or not account_id:
            reasons.append("missing account_id")
        elif account_id in seen_credit_accounts:
            reasons.append("duplicate account_id")
        else:
            seen_credit_accounts.add(account_id)
        if account.get("user_id") != user_id:
            reasons.append("credit account owner does not match verified user")
        if account.get("account_status") != "ACTIVE":
            reasons.append("credit account is not ACTIVE")

        if reasons:
            credit_exclusions.append({"account": credit_view(account), "reasons": reasons})
        elif payload.get("reported_lost_or_stolen") is True:
            credit_offers.append(credit_view(account))

    result = {
        "blocking_errors": errors,
        "debit_freeze_candidates": debit_candidates,
        "debit_exclusions": debit_exclusions,
        "credit_replacement_offer_accounts": credit_offers,
        "credit_exclusions": credit_exclusions,
        "required_human_steps": [
            "Confirm two identity fields and log verification before any banking action.",
            "Confirm each debit-card target and give required freeze disclosures before freezing.",
            "For a lost or stolen wallet, recommend closure as the permanent debit-card alternative and offer protection for active credit cards.",
            "Do not submit a credit replacement without explicit authorization, confirmed address, reason, shipping choice, applicable fee acknowledgement, and eligibility checks.",
            "For a requested human handoff, summarize each card's distinct current status and any outstanding replacement or closure request."
        ],
        "non_action_notice": "This plan is not authorization and does not execute a freeze, unfreeze, closure, transfer, or replacement order."
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
