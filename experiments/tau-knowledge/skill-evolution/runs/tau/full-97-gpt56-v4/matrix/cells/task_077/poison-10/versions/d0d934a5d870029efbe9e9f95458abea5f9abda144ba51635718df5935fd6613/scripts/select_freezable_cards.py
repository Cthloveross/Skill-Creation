#!/usr/bin/env python3
"""Select debit cards eligible for a verified customer's freeze request.

Reads the JSON schema documented in SKILL.md from stdin and emits a JSON object.
This utility performs no external calls and never carries out a banking action.
"""

import json
import sys


def as_string_set(value, field, errors):
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        errors.append(f"{field} must be an array of nonempty strings")
        return set()
    return set(value)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"eligible_cards": [], "ineligible_cards": [], "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"eligible_cards": [], "ineligible_cards": [], "errors": ["input must be a JSON object"]}))
        return

    errors = []
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id must be a nonempty string")

    selected = as_string_set(payload.get("selected_account_ids"), "selected_account_ids", errors)
    open_checking = as_string_set(payload.get("open_checking_account_ids"), "open_checking_account_ids", errors)
    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    eligible = []
    ineligible = []
    seen_card_ids = set()
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            ineligible.append({"index": index, "reasons": ["card record is not an object"]})
            continue
        card_id = card.get("card_id")
        reasons = []
        if not isinstance(card_id, str) or not card_id:
            reasons.append("missing card_id")
        elif card_id in seen_card_ids:
            reasons.append("duplicate card_id")
        else:
            seen_card_ids.add(card_id)
        if card.get("user_id") != user_id:
            reasons.append("card user_id does not match verified user")
        account_id = card.get("account_id")
        if account_id not in selected:
            reasons.append("card account is outside selected scope")
        if account_id not in open_checking:
            reasons.append("linked account is not a confirmed open checking account")
        if card.get("status") != "ACTIVE":
            reasons.append("card status is not ACTIVE")

        summary = {
            "card_id": card_id,
            "account_id": account_id,
            "status": card.get("status"),
        }
        if reasons:
            summary["reasons"] = reasons
            ineligible.append(summary)
        else:
            eligible.append(summary)

    print(json.dumps({
        "eligible_cards": eligible,
        "ineligible_cards": ineligible,
        "errors": errors,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
