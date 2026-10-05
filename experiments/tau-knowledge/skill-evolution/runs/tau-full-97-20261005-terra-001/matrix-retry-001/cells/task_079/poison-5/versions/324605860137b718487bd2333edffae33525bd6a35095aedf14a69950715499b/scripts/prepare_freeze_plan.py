#!/usr/bin/env python3
"""Create a non-executing debit-card freeze plan from normalized lookup data.

Input and output are JSON objects on stdin/stdout. This helper never calls tools.
"""

import json
import sys
from typing import Any, Dict, List


def issue(kind: str, message: str, **details: Any) -> Dict[str, Any]:
    item: Dict[str, Any] = {"type": kind, "message": message}
    item.update(details)
    return item


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    blockers: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    already_protected: List[Dict[str, Any]] = []
    not_actionable: List[Dict[str, Any]] = []

    user_id = payload.get("user_id")
    verified = payload.get("verified") is True
    disclosures_given = payload.get("disclosures_given") is True
    selected = payload.get("selected_account_ids")
    accounts = payload.get("accounts")
    cards_by_account = payload.get("cards_by_account")

    if not isinstance(user_id, str) or not user_id.strip():
        blockers.append(issue("identity", "A nonempty verified user_id is required."))
    if not verified:
        blockers.append(issue("identity", "Identity verification is not marked complete."))
    if not disclosures_given:
        blockers.append(issue("disclosure", "Required freeze disclosures are not marked complete."))
    if not isinstance(selected, list) or not selected or any(
        not isinstance(x, str) or not x.strip() for x in (selected or [])
    ):
        blockers.append(issue("scope", "selected_account_ids must be a nonempty list of confirmed account IDs."))
        selected = []
    if len(set(selected)) != len(selected):
        blockers.append(issue("scope", "selected_account_ids contains duplicate account IDs."))
    if not isinstance(accounts, list):
        blockers.append(issue("input", "accounts must be a list of normalized account records."))
        accounts = []
    if not isinstance(cards_by_account, dict):
        blockers.append(issue("input", "cards_by_account must be an object keyed by account ID."))
        cards_by_account = {}

    account_index: Dict[str, Dict[str, Any]] = {}
    for account in accounts:
        if not isinstance(account, dict):
            blockers.append(issue("input", "An account record is not an object."))
            continue
        account_id = account.get("account_id")
        if isinstance(account_id, str) and account_id:
            account_index[account_id] = account

    for account_id in selected:
        account = account_index.get(account_id)
        if account is None:
            blockers.append(issue("scope", "Selected account was not found in account lookup.", account_id=account_id))
            continue
        if account.get("account_type") != "checking":
            blockers.append(issue("eligibility", "Selected account is not a checking account.", account_id=account_id))
            continue
        cards = cards_by_account.get(account_id)
        if not isinstance(cards, list):
            blockers.append(issue("lookup", "No usable debit-card lookup list was supplied for selected account.", account_id=account_id))
            continue
        if not cards:
            not_actionable.append({
                "account_id": account_id,
                "reason": "No debit cards were returned for this checking account."
            })
            continue

        for card in cards:
            if not isinstance(card, dict):
                blockers.append(issue("input", "A debit-card record is not an object.", account_id=account_id))
                continue
            card_id = card.get("card_id")
            card_account_id = card.get("account_id")
            card_user_id = card.get("user_id")
            status = card.get("status")
            safe_card = {
                "account_id": account_id,
                "card_id": card_id,
                "card_number_last_4": card.get("card_number_last_4"),
                "status": status,
            }
            if not isinstance(card_id, str) or not card_id:
                blockers.append(issue("card_details", "Card record has no usable card_id.", account_id=account_id))
                continue
            if card_account_id != account_id:
                blockers.append(issue("ownership", "Card account_id does not match the queried account.", **safe_card))
                continue
            if card_user_id != user_id:
                blockers.append(issue("ownership", "Card user_id does not match the verified customer.", **safe_card))
                continue
            if status == "ACTIVE":
                actions.append({
                    "account_id": account_id,
                    "card_id": card_id,
                    "card_number_last_4": card.get("card_number_last_4"),
                    "tool": "freeze_debit_card_3892",
                    "arguments": {"card_id": card_id},
                })
            elif status == "FROZEN":
                already_protected.append({**safe_card, "reason": "Card is already frozen."})
            else:
                not_actionable.append({
                    **safe_card,
                    "reason": "Only ACTIVE debit cards are eligible for a freeze."
                })

    return {
        "ready_for_execution": bool(actions) and not any(
            entry["type"] in {"identity", "disclosure", "scope", "input"} for entry in blockers
        ),
        "actions": actions,
        "already_protected": already_protected,
        "not_actionable": not_actionable,
        "blockers": blockers,
        "summary": {
            "freeze_actions": len(actions),
            "already_frozen": len(already_protected),
            "not_actionable": len(not_actionable),
            "blockers": len(blockers),
        },
    }


def run() -> None:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Top-level input must be a JSON object.")
        result = main(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "ready_for_execution": False,
            "actions": [],
            "already_protected": [],
            "not_actionable": [],
            "blockers": [{"type": "input", "message": str(exc)}],
            "summary": {"freeze_actions": 0, "already_frozen": 0, "not_actionable": 0, "blockers": 1},
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    run()
