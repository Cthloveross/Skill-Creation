#!/usr/bin/env python3
"""Select unambiguous debit cards eligible for a verified customer's freeze request.

Input and output are JSON as documented in SKILL.md.  This utility performs no
external calls and never carries out a banking action.
"""
import json
import sys


def result(eligible=None, ineligible=None, errors=None):
    return {"eligible_cards": eligible or [], "ineligible_cards": ineligible or [], "errors": errors or []}


def nonempty_string_set(value, field, errors):
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        errors.append(f"{field} must be an array of nonempty strings")
        return set()
    return set(value)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(result(errors=[f"invalid JSON: {exc.msg}"],), sort_keys=True))
        return
    if not isinstance(payload, dict):
        print(json.dumps(result(errors=["input must be a JSON object"]), sort_keys=True))
        return

    errors = []
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id must be a nonempty string")
    selected = nonempty_string_set(payload.get("selected_account_ids"), "selected_account_ids", errors)
    open_checking = nonempty_string_set(payload.get("open_checking_account_ids"), "open_checking_account_ids", errors)
    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    # A duplicate returned ID is ambiguous: exclude every occurrence, not merely
    # later records, so a caller cannot accidentally freeze it once.
    id_counts = {}
    for card in cards:
        if isinstance(card, dict) and isinstance(card.get("card_id"), str) and card["card_id"]:
            id_counts[card["card_id"]] = id_counts.get(card["card_id"], 0) + 1

    eligible, ineligible = [], []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            ineligible.append({"index": index, "reasons": ["card record is not an object"]})
            continue
        card_id, account_id, status = card.get("card_id"), card.get("account_id"), card.get("status")
        reasons = []
        if not isinstance(card_id, str) or not card_id:
            reasons.append("missing card_id")
        elif id_counts[card_id] != 1:
            reasons.append("duplicate card_id makes card selection ambiguous")
        if card.get("user_id") != user_id:
            reasons.append("card user_id does not match verified user")
        if account_id not in selected:
            reasons.append("card account is outside selected scope")
        if account_id not in open_checking:
            reasons.append("linked account is not a confirmed open checking account")
        if status != "ACTIVE":
            reasons.append("card status is not ACTIVE")
        summary = {"card_id": card_id, "account_id": account_id, "status": status}
        if reasons:
            summary["reasons"] = reasons
            ineligible.append(summary)
        else:
            eligible.append(summary)
    print(json.dumps(result(eligible, ineligible, errors), sort_keys=True))


if __name__ == "__main__":
    main()
