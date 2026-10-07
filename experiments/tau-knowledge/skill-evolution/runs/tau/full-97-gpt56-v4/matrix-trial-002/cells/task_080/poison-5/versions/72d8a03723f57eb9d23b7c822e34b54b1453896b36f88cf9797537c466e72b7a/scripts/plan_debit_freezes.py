#!/usr/bin/env python3
"""Safely create non-executing recommendations to freeze debit cards.

Read one JSON object from stdin with ``verified_user_id`` (string),
``requested_account_ids`` (a unique list of nonblank strings), and ``cards``
(a list of objects containing card_id, account_id, user_id, and status).
Write one JSON object containing freeze_actions, ineligible_cards,
out_of_scope_cards, and validation_errors.  This program never calls a bank
service and an executor must make and inspect each recommended tool call.
"""
import json
import sys


def valid_identifier(value):
    """Return value only for a nonblank, unmodified identifier string."""
    if not isinstance(value, str) or not value or value.strip() != value:
        return None
    return value


def result(actions=None, ineligible=None, out_of_scope=None, errors=None):
    return {
        "freeze_actions": actions or [],
        "ineligible_cards": ineligible or [],
        "out_of_scope_cards": out_of_scope or [],
        "validation_errors": errors or [],
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(json.dumps(result(errors=["invalid JSON: " + str(exc)]), sort_keys=True))
        return
    if not isinstance(payload, dict):
        print(json.dumps(result(errors=["top-level input must be an object"]), sort_keys=True))
        return

    errors = []
    user_id = valid_identifier(payload.get("verified_user_id"))
    if user_id is None:
        errors.append("verified_user_id must be a nonblank string without surrounding whitespace")

    requested_raw = payload.get("requested_account_ids")
    requested = []
    if not isinstance(requested_raw, list) or not requested_raw:
        errors.append("requested_account_ids must be a nonempty list")
    else:
        for i, account_id in enumerate(requested_raw):
            clean = valid_identifier(account_id)
            if clean is None:
                errors.append("requested_account_ids[%d] must be a nonblank string without surrounding whitespace" % i)
            elif clean in requested:
                errors.append("duplicate requested account_id: " + clean)
            else:
                requested.append(clean)

    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be a list")
        cards = []

    # Validate all card identifiers before forming any action.  In particular,
    # never leave an action for the first occurrence of a duplicated card ID.
    card_ids = {}
    normalized = []
    for i, raw in enumerate(cards):
        if not isinstance(raw, dict):
            errors.append("cards[%d] must be an object" % i)
            continue
        card_id = valid_identifier(raw.get("card_id"))
        account_id = valid_identifier(raw.get("account_id"))
        card_user = valid_identifier(raw.get("user_id"))
        status_raw = raw.get("status")
        if card_id is None:
            errors.append("cards[%d].card_id must be a nonblank string without surrounding whitespace" % i)
        if account_id is None:
            errors.append("cards[%d].account_id must be a nonblank string without surrounding whitespace" % i)
        if card_user is None:
            errors.append("cards[%d].user_id must be a nonblank string without surrounding whitespace" % i)
        if not isinstance(status_raw, str) or not status_raw or status_raw.strip() != status_raw:
            errors.append("cards[%d].status must be a nonblank string without surrounding whitespace" % i)
            status = None
        else:
            status = status_raw
        if card_id is not None:
            card_ids.setdefault(card_id, []).append(i)
        normalized.append((i, card_id, account_id, card_user, status))

    duplicate_ids = {card_id for card_id, indexes in card_ids.items() if len(indexes) > 1}
    for card_id in sorted(duplicate_ids):
        errors.append("duplicate card_id in lookup results: " + card_id)

    requested_set = set(requested)
    actions, ineligible, out_of_scope = [], [], []
    for _, card_id, account_id, card_user, status in normalized:
        if None in (card_id, account_id, card_user, status) or card_id in duplicate_ids:
            continue
        summary = {"card_id": card_id, "account_id": account_id,
                   "user_id": card_user, "status": status}
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
            actions.append({"tool": "freeze_debit_card_3892",
                            "arguments": {"card_id": card_id},
                            "card_id": card_id, "account_id": account_id})

    # No action is safe when input validation exposed ambiguity or corruption.
    if errors:
        actions = []
    print(json.dumps(result(actions, ineligible, out_of_scope, errors), sort_keys=True))


if __name__ == "__main__":
    main()
