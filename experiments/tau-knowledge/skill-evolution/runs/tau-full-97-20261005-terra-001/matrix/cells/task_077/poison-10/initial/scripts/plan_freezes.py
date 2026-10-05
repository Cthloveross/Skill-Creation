#!/usr/bin/env python3
"""Plan eligible temporary debit-card freezes from freshly retrieved records.

Input: JSON described in SKILL.md on stdin.
Output: a JSON object containing a deterministic, non-executing action plan.
"""

import json
import sys
from typing import Any, Dict, List, Set


def as_list(value: Any, field: str, errors: List[str]) -> List[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be a list when provided")
        return []
    return value


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def is_checking(account: Dict[str, Any]) -> bool:
    return text(account.get("account_type")).upper() == "CHECKING"


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return {"eligible_actions": [], "ineligible": [], "unmatched_requested_card_ids": [],
                "validation_errors": ["input must be a JSON object"]}

    user_id = text(payload.get("user_id"))
    if not payload.get("verified"):
        errors.append("identity verification has not succeeded")
    if not user_id:
        errors.append("user_id is required")

    accounts = as_list(payload.get("accounts"), "accounts", errors)
    cards = as_list(payload.get("cards"), "cards", errors)
    raw_requested_cards = payload.get("requested_card_ids")
    raw_requested_accounts = payload.get("requested_account_ids")
    requested_cards_provided = raw_requested_cards is not None
    requested_accounts_provided = raw_requested_accounts is not None
    requested_card_ids = as_list(raw_requested_cards, "requested_card_ids", errors)
    requested_account_ids = as_list(raw_requested_accounts, "requested_account_ids", errors)

    account_by_id: Dict[str, Dict[str, Any]] = {}
    for account in accounts:
        if not isinstance(account, dict):
            errors.append("each accounts item must be an object")
            continue
        account_id = text(account.get("account_id"))
        if not account_id:
            errors.append("each account requires account_id")
            continue
        account_by_id[account_id] = account

    selected_accounts: Set[str] = set()
    requested_account_set = {text(x) for x in requested_account_ids if text(x)}
    if requested_accounts_provided:
        for account_id in requested_account_set:
            account = account_by_id.get(account_id)
            if account is None:
                errors.append(f"requested account not found: {account_id}")
            elif not is_checking(account):
                errors.append(f"requested account is not a checking account: {account_id}")
            else:
                account_owner = text(account.get("user_id"))
                if account_owner and account_owner != user_id:
                    errors.append(f"requested account is not owned by verified user: {account_id}")
                else:
                    selected_accounts.add(account_id)
    else:
        for account_id, account in account_by_id.items():
            account_owner = text(account.get("user_id"))
            if is_checking(account) and (not account_owner or account_owner == user_id):
                selected_accounts.add(account_id)

    requested_set = {text(x) for x in requested_card_ids if text(x)}
    if requested_cards_provided and not requested_set:
        errors.append("requested_card_ids was supplied but contains no card IDs")

    seen_cards: Set[str] = set()
    found_requested: Set[str] = set()
    eligible: List[Dict[str, str]] = []
    ineligible: List[Dict[str, str]] = []

    for card in cards:
        if not isinstance(card, dict):
            errors.append("each cards item must be an object")
            continue
        card_id = text(card.get("card_id"))
        account_id = text(card.get("account_id"))
        card_owner = text(card.get("user_id"))
        status = text(card.get("status")).upper()
        if not card_id or not account_id or not card_owner or not status:
            errors.append("each card requires card_id, account_id, user_id, and status")
            continue
        if card_id in seen_cards:
            continue
        seen_cards.add(card_id)

        if requested_cards_provided and card_id not in requested_set:
            continue
        if card_id in requested_set:
            found_requested.add(card_id)

        reason = ""
        if account_id not in selected_accounts:
            reason = "card is not linked to a selected checking account"
        elif card_owner != user_id:
            reason = "card is not owned by the verified user"
        elif status != "ACTIVE":
            reason = f"card status is {status}, not ACTIVE"

        if reason:
            ineligible.append({"card_id": card_id, "account_id": account_id, "reason": reason})
        else:
            eligible.append({"card_id": card_id, "account_id": account_id})

    unmatched = sorted(requested_set - found_requested) if requested_cards_provided else []
    if not selected_accounts and not errors:
        errors.append("no eligible checking accounts were selected")

    return {
        "eligible_actions": eligible,
        "ineligible": ineligible,
        "unmatched_requested_card_ids": unmatched,
        "validation_errors": errors,
        "selected_checking_account_ids": sorted(selected_accounts),
    }


def run() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:  # Keep stdout machine-readable for callers.
        result = {
            "eligible_actions": [],
            "ineligible": [],
            "unmatched_requested_card_ids": [],
            "validation_errors": [f"invalid JSON input: {exc}"],
        }
    else:
        result = main(payload)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    run()
