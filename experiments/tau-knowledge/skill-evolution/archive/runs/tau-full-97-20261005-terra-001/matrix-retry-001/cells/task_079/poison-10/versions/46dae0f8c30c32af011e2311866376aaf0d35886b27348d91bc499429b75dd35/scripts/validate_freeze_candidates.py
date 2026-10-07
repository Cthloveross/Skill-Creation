#!/usr/bin/env python3
"""Validate structured debit-card lookup results for a freeze workflow.

Reads JSON from stdin and writes JSON to stdout. This helper is deliberately
read-only: it only selects individually eligible ACTIVE cards and reports
exceptions for the calling agent to resolve.
"""

import json
import sys
from typing import Any, Dict, List


def text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def upper(value: Any) -> str:
    return text(value).upper()


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    blocked: List[Dict[str, str]] = []
    unresolved: List[Dict[str, str]] = []
    freeze_ids: List[str] = []
    frozen_ids: List[str] = []

    user_id = text(payload.get("verified_user_id"))
    accounts = payload.get("accounts")
    cards_by_account = payload.get("cards_by_account")
    lookup_errors = payload.get("lookup_errors", [])
    target_ids = payload.get("target_account_ids")

    if not user_id:
        errors.append("verified_user_id is required")
    if not isinstance(accounts, list):
        errors.append("accounts must be an array")
        accounts = []
    if not isinstance(cards_by_account, dict):
        errors.append("cards_by_account must be an object keyed by account_id")
        cards_by_account = {}
    if lookup_errors:
        if isinstance(lookup_errors, list):
            errors.append("lookup_errors were supplied; resolve retrieval failures before freezing")
        else:
            errors.append("lookup_errors must be an array when supplied")
    if target_ids is not None and not isinstance(target_ids, list):
        errors.append("target_account_ids must be an array when supplied")
        target_ids = []

    account_map: Dict[str, Dict[str, Any]] = {}
    for account in accounts:
        if not isinstance(account, dict):
            errors.append("each account must be an object")
            continue
        account_id = text(account.get("account_id"))
        if not account_id:
            errors.append("an account record is missing account_id")
            continue
        if account_id in account_map:
            errors.append("duplicate account_id in accounts: " + account_id)
            continue
        account_map[account_id] = account

    if target_ids is None:
        selected_ids: List[str] = []
        for account_id, account in account_map.items():
            account_type = upper(account.get("account_type"))
            if account_type == "CHECKING":
                selected_ids.append(account_id)
            elif not account_type:
                unresolved.append({
                    "account_id": account_id,
                    "reason": "account_type missing; cannot determine whether debit cards are in scope",
                })
    else:
        selected_ids = []
        for raw_id in target_ids:
            account_id = text(raw_id)
            if not account_id or account_id not in account_map:
                unresolved.append({
                    "account_id": account_id or "(missing)",
                    "reason": "requested account was not returned by the customer account lookup",
                })
                continue
            if upper(account_map[account_id].get("account_type")) != "CHECKING":
                unresolved.append({
                    "account_id": account_id,
                    "reason": "requested account is not a checking account",
                })
                continue
            selected_ids.append(account_id)

    if not selected_ids and not unresolved:
        errors.append("no selected checking accounts were available for card lookup")

    for account_id in selected_ids:
        if account_id not in cards_by_account:
            unresolved.append({
                "account_id": account_id,
                "reason": "no debit-card lookup result was supplied for this selected account",
            })
            continue
        cards = cards_by_account[account_id]
        if not isinstance(cards, list):
            unresolved.append({
                "account_id": account_id,
                "reason": "debit-card lookup result must be an array",
            })
            continue
        for card in cards:
            if not isinstance(card, dict):
                blocked.append({"card_id": "(unknown)", "account_id": account_id, "reason": "malformed card record"})
                continue
            card_id = text(card.get("card_id"))
            record_account_id = text(card.get("account_id"))
            card_user_id = text(card.get("user_id"))
            status = upper(card.get("status"))
            label = card_id or "(missing)"
            if not card_id:
                blocked.append({"card_id": label, "account_id": account_id, "reason": "card_id missing"})
            elif record_account_id != account_id:
                blocked.append({"card_id": label, "account_id": account_id, "reason": "card account_id does not match selected account"})
            elif card_user_id != user_id:
                blocked.append({"card_id": label, "account_id": account_id, "reason": "card user_id does not match verified customer"})
            elif status == "ACTIVE":
                freeze_ids.append(card_id)
            elif status == "FROZEN":
                frozen_ids.append(card_id)
            else:
                blocked.append({
                    "card_id": label,
                    "account_id": account_id,
                    "reason": "card is not eligible for freeze because status is " + (status or "missing"),
                })

    # Duplicates imply inconsistent lookup data and should not produce duplicate actions.
    if len(freeze_ids) != len(set(freeze_ids)):
        errors.append("duplicate eligible card_id returned; resolve duplicate lookup data before freezing")
        freeze_ids = list(dict.fromkeys(freeze_ids))
    frozen_ids = list(dict.fromkeys(frozen_ids))

    return {
        "valid": not errors and not unresolved,
        "selected_account_ids": selected_ids,
        "freeze_card_ids": freeze_ids,
        "already_frozen_card_ids": frozen_ids,
        "blocked_cards": blocked,
        "unresolved_accounts": unresolved,
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object")
        result = main(raw)
    except Exception as exc:  # Return machine-readable validation failure.
        result = {
            "valid": False,
            "selected_account_ids": [],
            "freeze_card_ids": [],
            "already_frozen_card_ids": [],
            "blocked_cards": [],
            "unresolved_accounts": [],
            "errors": [str(exc)],
        }
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
