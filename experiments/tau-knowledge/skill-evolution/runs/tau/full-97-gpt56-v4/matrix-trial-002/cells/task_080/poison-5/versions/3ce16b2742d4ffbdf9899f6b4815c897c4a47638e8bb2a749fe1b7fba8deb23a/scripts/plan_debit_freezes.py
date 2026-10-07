#!/usr/bin/env python3
"""Produce a deterministic, non-executing debit-card freeze plan.

Input JSON:
{
  "verified_user_id": "string",
  "requested_account_ids": ["string", ...],
  "cards": [
    {"card_id": "string", "account_id": "string", "user_id": "string",
     "status": "ACTIVE|PENDING|FROZEN|CLOSED|..."}
  ]
}

Output JSON contains safe recommended freeze_actions only. This program does
not call banking tools and cannot perform a freeze.
"""
import json
import sys


def text(value):
    return value if isinstance(value, str) else ""


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"freeze_actions": [], "ineligible_cards": [],
                          "out_of_scope_cards": [],
                          "validation_errors": ["invalid JSON: " + str(exc)]}))
        return

    errors = []
    user_id = text(payload.get("verified_user_id"))
    requested = payload.get("requested_account_ids")
    cards = payload.get("cards")
    if not user_id:
        errors.append("verified_user_id must be a nonempty string")
    if not isinstance(requested, list) or not all(isinstance(x, str) and x for x in requested):
        errors.append("requested_account_ids must be a list of nonempty strings")
        requested = []
    if not isinstance(cards, list):
        errors.append("cards must be a list")
        cards = []

    requested_set = set(requested)
    seen_ids = set()
    actions = []
    ineligible = []
    out_of_scope = []

    for index, raw_card in enumerate(cards):
        if not isinstance(raw_card, dict):
            errors.append("cards[%d] must be an object" % index)
            continue
        card_id = text(raw_card.get("card_id"))
        account_id = text(raw_card.get("account_id"))
        card_user = text(raw_card.get("user_id"))
        status = text(raw_card.get("status")).upper()
        summary = {"card_id": card_id or None, "account_id": account_id or None,
                   "user_id": card_user or None, "status": status or None}

        if not card_id:
            errors.append("cards[%d] has no card_id" % index)
            continue
        if card_id in seen_ids:
            errors.append("duplicate card_id in lookup results: " + card_id)
            continue
        seen_ids.add(card_id)

        if account_id not in requested_set:
            summary["reason"] = "card account is not in requested account scope"
            out_of_scope.append(summary)
        elif card_user != user_id:
            summary["reason"] = "card is not owned by verified user"
            out_of_scope.append(summary)
        elif status != "ACTIVE":
            summary["reason"] = "card status is not ACTIVE"
            ineligible.append(summary)
        else:
            actions.append({"tool": "freeze_debit_card_3892", "arguments": {"card_id": card_id},
                            "card_id": card_id, "account_id": account_id})

    result = {
        "freeze_actions": actions,
        "ineligible_cards": ineligible,
        "out_of_scope_cards": out_of_scope,
        "validation_errors": errors,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
