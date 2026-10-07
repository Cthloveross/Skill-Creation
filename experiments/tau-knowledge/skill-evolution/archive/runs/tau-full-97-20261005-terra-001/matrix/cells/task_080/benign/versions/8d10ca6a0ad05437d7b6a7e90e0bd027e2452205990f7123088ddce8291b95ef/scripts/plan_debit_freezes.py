#!/usr/bin/env python3
"""Create a conservative debit-card freeze plan from structured lookup results.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no external calls and deliberately leaves ambiguous selections unresolved.
"""
import json
import sys


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def account_label(account):
    for key in ("account_class", "account_name", "display_name", "name"):
        value = account.get(key)
        if value:
            return str(value)
    return ""


def result(freeze_ids, selected, blockers):
    return {
        "freeze_card_ids": freeze_ids,
        "selected_cards": selected,
        "blockers": blockers,
    }


def main(payload):
    required = (
        "verified_user_id",
        "requested_debit_account_labels",
        "accounts",
        "debit_cards",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        return result([], [], [{
            "type": "invalid_input",
            "detail": "Missing: " + ", ".join(missing),
        }])

    user_id = str(payload["verified_user_id"] or "")
    requested_labels = payload["requested_debit_account_labels"]
    accounts = payload["accounts"]
    cards = payload["debit_cards"]
    blockers = []
    selected = []
    freeze_ids = []

    if not user_id:
        return result([], [], [{
            "type": "unverified_user",
            "detail": "verified_user_id is empty",
        }])
    if not isinstance(requested_labels, list):
        return result([], [], [{
            "type": "invalid_input",
            "detail": "requested_debit_account_labels must be an array",
        }])
    if not isinstance(accounts, list) or not isinstance(cards, list):
        return result([], [], [{
            "type": "invalid_input",
            "detail": "accounts and debit_cards must be arrays",
        }])
    if not all(isinstance(item, dict) for item in accounts + cards):
        return result([], [], [{
            "type": "invalid_input",
            "detail": "accounts and debit_cards must contain objects",
        }])

    seen_labels = set()
    for requested in requested_labels:
        wanted = norm(requested)
        if not wanted or wanted in seen_labels:
            continue
        seen_labels.add(wanted)
        matches = [
            account for account in accounts
            if norm(account.get("account_type")) == "checking"
            and norm(account_label(account)) == wanted
        ]
        if len(matches) != 1:
            blockers.append({
                "type": "account_not_unique" if matches else "account_not_found",
                "requested_label": requested,
                "matching_account_ids": [
                    account.get("account_id") for account in matches
                    if account.get("account_id")
                ],
            })
            continue

        account = matches[0]
        account_id = account.get("account_id")
        if not account_id:
            blockers.append({
                "type": "account_missing_id",
                "requested_label": requested,
            })
            continue

        owned = [
            card for card in cards
            if card.get("account_id") == account_id
            and card.get("user_id") == user_id
        ]
        active = [
            card for card in owned
            if norm(card.get("status")) == "active"
        ]
        if len(active) != 1:
            blockers.append({
                "type": "multiple_active_cards" if len(active) > 1 else "no_active_owned_card",
                "requested_label": requested,
                "account_id": account_id,
                "owned_cards": [
                    {
                        "card_id": card.get("card_id"),
                        "last4": card.get("card_number_last_4"),
                        "status": card.get("status"),
                    }
                    for card in owned
                ],
            })
            continue

        card = active[0]
        card_id = card.get("card_id")
        if not card_id:
            blockers.append({
                "type": "card_missing_id",
                "requested_label": requested,
                "account_id": account_id,
            })
            continue
        freeze_ids.append(card_id)
        selected.append({
            "requested_label": requested,
            "account_id": account_id,
            "card_id": card_id,
            "last4": card.get("card_number_last_4"),
            "status": card.get("status"),
        })

    return result(freeze_ids, selected, blockers)


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps(result([], [], [{
            "type": "invalid_input",
            "detail": str(exc),
        }]), sort_keys=True))
