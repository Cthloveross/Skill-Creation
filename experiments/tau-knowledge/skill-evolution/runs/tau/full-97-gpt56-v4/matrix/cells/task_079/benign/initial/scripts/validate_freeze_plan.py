#!/usr/bin/env python3
"""Validate normalized account/card lookup results for debit-card freeze eligibility.

Reads one JSON object from stdin and emits one JSON object on stdout. This performs no
bank actions. Account/card values must be copied from current runtime lookup responses.
"""
import json
import sys


def text(value):
    return value if isinstance(value, str) else ""


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": "invalid_json", "detail": str(exc)}))
        return 2
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "error": "input_must_be_object"}))
        return 2

    user_id = text(data.get("verified_user_id"))
    accounts = data.get("accounts")
    cards = data.get("cards")
    if not user_id or not isinstance(accounts, list) or not isinstance(cards, list):
        print(json.dumps({
            "ok": False,
            "error": "required_fields",
            "detail": "verified_user_id (string), accounts (array), and cards (array) are required"
        }))
        return 2

    checking_ids = set()
    for account in accounts:
        if not isinstance(account, dict):
            continue
        account_id = text(account.get("account_id"))
        # The card lookup source only supports checking accounts. Status is deliberately
        # not used as an added freeze condition; the documented card requirement is ACTIVE.
        if account_id and text(account.get("account_type")).strip().lower() == "checking":
            checking_ids.add(account_id)

    eligible = []
    excluded = []
    seen = set()
    for card in cards:
        if not isinstance(card, dict):
            excluded.append({"card_id": None, "reason": "malformed_card_record"})
            continue
        card_id = text(card.get("card_id"))
        reasons = []
        if not card_id:
            reasons.append("missing_card_id")
        if text(card.get("user_id")) != user_id:
            reasons.append("owner_does_not_match_verified_user")
        if text(card.get("account_id")) not in checking_ids:
            reasons.append("not_linked_to_retrieved_checking_account")
        if text(card.get("status")).upper() != "ACTIVE":
            reasons.append("card_status_not_active")
        if card_id in seen:
            reasons.append("duplicate_card_id")
        if reasons:
            excluded.append({"card_id": card_id or None, "reason": ";".join(reasons)})
        else:
            seen.add(card_id)
            eligible.append(card_id)

    print(json.dumps({
        "ok": True,
        "eligible_card_ids": eligible,
        "excluded": excluded,
        "checking_account_ids_considered": sorted(checking_ids)
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
