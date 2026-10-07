#!/usr/bin/env python3
"""Create a conservative debit-card freeze plan from structured lookup results.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no external calls and intentionally leaves ambiguous selections unresolved.
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


def main(payload):
    required = ("verified_user_id", "requested_debit_account_labels", "accounts", "debit_cards")
    missing = [key for key in required if key not in payload]
    if missing:
        return {"freeze_card_ids": [], "selected_cards": [],
                "blockers": [{"type": "invalid_input", "detail": "Missing: " + ", ".join(missing)}]}

    user_id = str(payload["verified_user_id"] or "")
    blockers = []
    selected = []
    freeze_ids = []
    accounts = payload["accounts"]
    cards = payload["debit_cards"]
    if not user_id:
        blockers.append({"type": "unverified_user", "detail": "verified_user_id is empty"})
        return {"freeze_card_ids": freeze_ids, "selected_cards": selected, "blockers": blockers}
    if not isinstance(accounts, list) or not isinstance(cards, list):
        blockers.append({"type": "invalid_input", "detail": "accounts and debit_cards must be arrays"})
        return {"freeze_card_ids": freeze_ids, "selected_cards": selected, "blockers": blockers}

    seen_labels = set()
    for requested in payload["requested_debit_account_labels"]:
        wanted = norm(requested)
        if not wanted or wanted in seen_labels:
            continue
        seen_labels.add(wanted)
        matches = [a for a in accounts if norm(a.get("account_type")) == "checking" and norm(account_label(a)) == wanted]
        if len(matches) != 1:
            blockers.append({
                "type": "account_not_unique" if matches else "account_not_found",
                "requested_label": requested,
                "matching_account_ids": [a.get("account_id") for a in matches if a.get("account_id")],
            })
            continue

        account = matches[0]
        account_id = account.get("account_id")
        if not account_id:
            blockers.append({"type": "account_missing_id", "requested_label": requested})
            continue
        active = [c for c in cards if c.get("account_id") == account_id and c.get("user_id") == user_id and norm(c.get("status")) == "active"]
        owned = [c for c in cards if c.get("account_id") == account_id and c.get("user_id") == user_id]
        if len(active) != 1:
            blockers.append({
                "type": "multiple_active_cards" if len(active) > 1 else "no_active_owned_card",
                "requested_label": requested,
                "account_id": account_id,
                "owned_cards": [{"card_id": c.get("card_id"), "last4": c.get("card_number_last_4"), "status": c.get("status")} for c in owned],
            })
            continue
        card = active[0]
        card_id = card.get("card_id")
        if not card_id:
            blockers.append({"type": "card_missing_id", "requested_label": requested, "account_id": account_id})
            continue
        freeze_ids.append(card_id)
        selected.append({"requested_label": requested, "account_id": account_id,
                         "card_id": card_id, "last4": card.get("card_number_last_4"), "status": card.get("status")})

    return {"freeze_card_ids": freeze_ids, "selected_cards": selected, "blockers": blockers}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"freeze_card_ids": [], "selected_cards": [],
                          "blockers": [{"type": "invalid_input", "detail": str(exc)}]}, sort_keys=True))
