#!/usr/bin/env python3
"""Validate one debit-card restoration request without performing bank actions.

Reads one JSON object from stdin and emits one JSON object to stdout. The caller
must obtain current card and linked-account records before using this helper.
"""

import json
import sys


def text(value):
    return value if isinstance(value, str) and value else None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"eligible": False, "card_id": None,
                          "reasons": [f"invalid JSON: {exc.msg}"]}, sort_keys=True))
        return

    reasons = []
    requested_card_id = text(payload.get("requested_card_id"))
    user_id = text(payload.get("user_id"))
    card = payload.get("card")
    account = payload.get("linked_account")

    if payload.get("verified") is not True:
        reasons.append("customer is not verified")
    if user_id is None:
        reasons.append("user_id is required")
    if requested_card_id is None:
        reasons.append("requested_card_id is required")
    if not isinstance(card, dict):
        reasons.append("card must be an object")
        card = {}
    if not isinstance(account, dict):
        reasons.append("linked_account must be an object")
        account = {}

    card_id = text(card.get("card_id"))
    if card_id is None:
        reasons.append("card.card_id is required")
    elif requested_card_id is not None and card_id != requested_card_id:
        reasons.append("requested card does not match the retrieved card")

    if user_id is not None and card.get("user_id") != user_id:
        reasons.append("card ownership mismatch")
    if card.get("status") != "FROZEN":
        reasons.append("card status must be FROZEN")

    card_account_id = text(card.get("account_id"))
    account_id = text(account.get("account_id"))
    if card_account_id is None:
        reasons.append("card.account_id is required")
    elif account_id != card_account_id:
        reasons.append("linked account does not match the card account")
    if account.get("account_type") != "checking":
        reasons.append("linked account must be a checking account")
    if account.get("status") != "OPEN":
        reasons.append("linked checking account must be OPEN")

    print(json.dumps({
        "eligible": not reasons,
        "card_id": card_id if not reasons else None,
        "reasons": reasons,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
