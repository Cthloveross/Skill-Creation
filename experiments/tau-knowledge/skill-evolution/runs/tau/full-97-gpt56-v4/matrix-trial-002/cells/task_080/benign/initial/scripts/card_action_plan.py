#!/usr/bin/env python3
"""Produce conservative card-protection preflight guidance from JSON stdin.

Input:
{
  "verified": bool,
  "user_id": str,
  "cards": [
    {"kind": "debit"|"credit", "user_id": str, ...}
  ]
}

Debit fields: card_id, status, requested_action (freeze|close), optional reason.
Credit fields: account_id, in_wallet (bool), requested_action (replace|none).
Output: {"ok": bool, "actions": [...], "errors": [...]}.
This utility does not call tools or make eligibility determinations beyond data supplied.
"""
import json
import sys


def main(payload):
    errors = []
    actions = []
    verified = payload.get("verified") is True
    user_id = payload.get("user_id")
    cards = payload.get("cards")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id is required")
    if not isinstance(cards, list):
        return {"ok": False, "actions": [], "errors": errors + ["cards must be a list"]}
    if not verified:
        errors.append("No card-changing action: identity verification is not complete")

    for index, card in enumerate(cards):
        prefix = "cards[%d]" % index
        if not isinstance(card, dict):
            errors.append(prefix + " must be an object")
            continue
        kind = card.get("kind")
        owned = bool(user_id) and card.get("user_id") == user_id
        if kind not in ("debit", "credit"):
            errors.append(prefix + ".kind must be debit or credit")
            continue
        if not owned:
            actions.append({"index": index, "decision": "do_not_act", "reason": "card is not confirmed as owned by verified user"})
            continue
        if not verified:
            actions.append({"index": index, "decision": "do_not_act", "reason": "verification incomplete"})
            continue

        if kind == "debit":
            card_id = card.get("card_id")
            status = card.get("status")
            requested = card.get("requested_action")
            if not isinstance(card_id, str) or not card_id:
                errors.append(prefix + ".card_id is required for debit guidance")
                continue
            if requested == "freeze":
                if status == "ACTIVE":
                    actions.append({"index": index, "card_id": card_id, "decision": "eligible_to_freeze", "next_tool": "freeze_debit_card_3892"})
                else:
                    actions.append({"index": index, "card_id": card_id, "decision": "do_not_freeze", "reason": "freeze requires ACTIVE status", "status": status})
            elif requested == "close":
                if status in ("ACTIVE", "PENDING"):
                    actions.append({"index": index, "card_id": card_id, "decision": "needs_closure_prerequisite_checks", "checks": ["pending transactions", "pending refunds", "closure reason and policy eligibility"]})
                else:
                    actions.append({"index": index, "card_id": card_id, "decision": "do_not_close", "reason": "closure requires ACTIVE or PENDING status", "status": status})
            else:
                actions.append({"index": index, "card_id": card_id, "decision": "clarify_freeze_or_close"})
        else:
            account_id = card.get("account_id")
            in_wallet = card.get("in_wallet")
            requested = card.get("requested_action")
            if not isinstance(account_id, str) or not account_id:
                errors.append(prefix + ".account_id is required for credit guidance")
                continue
            if in_wallet is not True:
                actions.append({"index": index, "account_id": account_id, "decision": "ask_whether_card_was_in_wallet"})
            elif requested == "replace":
                actions.append({"index": index, "account_id": account_id, "decision": "collect_replacement_prerequisites", "required": ["reason", "confirmed shipping address", "shipping speed", "expedited fee acknowledgement if applicable", "eligibility confirmation"]})
            else:
                actions.append({"index": index, "account_id": account_id, "decision": "offer_replacement_not_credit_freeze"})
    return {"ok": not errors, "actions": actions, "errors": errors}


if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "actions": [], "errors": [str(exc)]}, separators=(",", ":")))
        sys.exit(1)
