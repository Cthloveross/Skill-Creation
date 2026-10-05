#!/usr/bin/env python3
"""Classify debit-card lookup results for the debit-card freeze procedure.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no external actions and deliberately does not infer missing facts.
"""

import json
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"eligible_card_ids": [], "already_frozen_card_ids": [],
                          "ineligible": [], "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    errors = []
    eligible = []
    already_frozen = []
    ineligible = []

    if payload.get("verified") is not True:
        errors.append("customer is not verified; no cards are eligible")
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id is required")

    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    seen = set()
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            ineligible.append({"index": index, "card_id": None, "reason": "invalid card record"})
            continue
        card_id = card.get("card_id")
        if not isinstance(card_id, str) or not card_id:
            ineligible.append({"index": index, "card_id": None, "reason": "missing card_id"})
            continue
        if card_id in seen:
            ineligible.append({"index": index, "card_id": card_id, "reason": "duplicate card_id"})
            continue
        seen.add(card_id)

        if payload.get("verified") is not True:
            ineligible.append({"index": index, "card_id": card_id, "reason": "customer not verified"})
        elif card.get("user_id") != user_id:
            ineligible.append({"index": index, "card_id": card_id, "reason": "card ownership mismatch"})
        elif card.get("status") == "ACTIVE":
            eligible.append(card_id)
        elif card.get("status") == "FROZEN":
            already_frozen.append(card_id)
        else:
            status = card.get("status")
            ineligible.append({"index": index, "card_id": card_id,
                               "reason": f"card status is not eligible for freeze: {status!r}"})

    print(json.dumps({
        "eligible_card_ids": eligible,
        "already_frozen_card_ids": already_frozen,
        "ineligible": ineligible,
        "errors": errors,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
