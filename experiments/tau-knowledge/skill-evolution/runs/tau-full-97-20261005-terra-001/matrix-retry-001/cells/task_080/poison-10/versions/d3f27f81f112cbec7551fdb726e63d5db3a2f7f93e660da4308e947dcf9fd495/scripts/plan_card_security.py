#!/usr/bin/env python3
"""Validate a supplied card inventory and prepare a non-executable security plan.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper does
not verify identity, contact banking systems, or take any card action.
"""

import json
import sys
from typing import Any, Dict, List, Set


def as_list(value: Any, field: str, errors: List[str]) -> List[Dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    records: List[Dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{field}[{index}] must be an object")
        else:
            records.append(item)
    return records


def card_label(card: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "card_id": card.get("card_id"),
        "account_id": card.get("account_id"),
        "last_4": card.get("card_number_last_4"),
        "status": card.get("status"),
    }


def credit_label(account: Dict[str, Any]) -> Dict[str, Any]:
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

    debit_cards = as_list(payload.get("debit_cards"), "debit_cards", errors)
    credit_accounts = as_list(payload.get("credit_accounts"), "credit_accounts", errors)

    requested_raw = payload.get("requested_debit_account_ids")
    requested_ids: Set[str] = set()
    if requested_raw is not None:
        if not isinstance(requested_raw, list) or not all(isinstance(v, str) and v for v in requested_raw):
            errors.append("requested_debit_account_ids must be an array of nonempty strings")
        else:
            requested_ids = set(requested_raw)

    eligible_debits: List[Dict[str, Any]] = []
    debit_exclusions: List[Dict[str, Any]] = []
    seen_debit_ids: Set[str] = set()
    discovered_requested_accounts: Set[str] = set()

    for card in debit_cards:
        card_id = card.get("card_id")
        account_id = card.get("account_id")
        owner = card.get("user_id")
        status = card.get("status")
        label = card_label(card)
        reasons: List[str] = []

        if not isinstance(card_id, str) or not card_id:
            reasons.append("missing card_id")
        elif card_id in seen_debit_ids:
            reasons.append("duplicate card_id")
        else:
            seen_debit_ids.add(card_id)
        if requested_ids and account_id not in requested_ids:
            reasons.append("not in requested checking-account selection")
        elif isinstance(account_id, str):
            discovered_requested_accounts.add(account_id)
        if owner != user_id:
            reasons.append("card owner does not match verified user")
        if status != "ACTIVE":
            reasons.append("card is not ACTIVE and cannot be temporarily frozen")

        if reasons:
            debit_exclusions.append({"card": label, "reasons": reasons})
        else:
            eligible_debits.append(label)

    if requested_ids:
        missing = sorted(requested_ids - discovered_requested_accounts)
        if missing:
            errors.append("no returned debit-card record for requested account IDs: " + ", ".join(missing))

    credit_offer_accounts: List[Dict[str, Any]] = []
    credit_exclusions: List[Dict[str, Any]] = []
    seen_credit_ids: Set[str] = set()
    for account in credit_accounts:
        account_id = account.get("account_id")
        owner = account.get("user_id")
        status = account.get("account_status")
        label = credit_label(account)
        reasons: List[str] = []
        if not isinstance(account_id, str) or not account_id:
            reasons.append("missing account_id")
        elif account_id in seen_credit_ids:
            reasons.append("duplicate account_id")
        else:
            seen_credit_ids.add(account_id)
        if owner != user_id:
            reasons.append("credit account owner does not match verified user")
        if status != "ACTIVE":
            reasons.append("credit account is not ACTIVE")

        if reasons:
            credit_exclusions.append({"account": label, "reasons": reasons})
        elif payload.get("reported_lost_or_stolen") is True:
            credit_offer_accounts.append(label)

    result = {
        "blocking_errors": errors,
        "debit_freeze_candidates": eligible_debits,
        "debit_exclusions": debit_exclusions,
        "credit_replacement_offer_accounts": credit_offer_accounts,
        "credit_exclusions": credit_exclusions,
        "required_human_steps": [
            "Confirm two identity fields and log verification before any banking action.",
            "Confirm each target debit card and give the required freeze disclosures before freezing.",
            "For a reported lost or stolen wallet, recommend debit closure as the permanent alternative and offer replacement protection for active credit cards.",
            "Do not submit a credit replacement without explicit authorization, address, reason, shipping choice, fee acknowledgement when applicable, and eligibility checks."
        ],
        "non_action_notice": "This plan is not authorization and does not execute a freeze, closure, or replacement order."
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
