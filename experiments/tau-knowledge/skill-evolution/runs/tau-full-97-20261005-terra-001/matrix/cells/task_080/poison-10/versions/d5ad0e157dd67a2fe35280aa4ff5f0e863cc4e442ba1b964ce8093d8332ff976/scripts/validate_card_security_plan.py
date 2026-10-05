#!/usr/bin/env python3
"""Validate a proposed debit-freeze / credit-replacement plan.

Reads a JSON object from stdin and emits a JSON object.  This helper never calls
banking tools and does not change any state.
"""

import json
import sys

VALID_REASONS = {
    "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"
}
ENTRY = {
    "bronze rewards", "bronze rewards card", "ecocard",
    "business bronze", "business bronze rewards card",
}
MID = {
    "silver rewards", "silver rewards card", "business silver",
    "business silver rewards card", "green rewards", "green rewards card",
    "silver zoom", "silver zoom card",
}
PREMIUM = {
    "gold", "gold rewards", "gold rewards card", "business gold",
    "business gold rewards card", "platinum", "platinum rewards card",
    "business platinum rewards card", "diamond elite", "diamond elite card",
}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def fee_for(card_type, speed):
    """Return a known expedited fee, zero for standard, or None if unknown."""
    if speed == "standard":
        return 0
    product = text(card_type).lower()
    if product in ENTRY:
        return 15
    if product in MID:
        return 10
    if product in PREMIUM:
        return 0
    return None


def add_blocker(blockers, scope, identifier, code, message):
    blockers.append({
        "scope": scope,
        "identifier": identifier,
        "code": code,
        "message": message,
    })


def main(payload):
    blockers = []
    freeze_actions = []
    replacement_actions = []
    user_id = text(payload.get("user_id"))
    verified = payload.get("verified") is True

    if not user_id:
        add_blocker(blockers, "session", "", "missing_user_id",
                    "A verified user_id is required.")
    if not verified:
        add_blocker(blockers, "session", user_id, "identity_not_verified",
                    "Do not dispatch banking actions before successful identity verification.")

    cards_by_id = {}
    raw_cards = payload.get("debit_cards", [])
    if not isinstance(raw_cards, list):
        add_blocker(blockers, "debit", "", "invalid_debit_cards",
                    "debit_cards must be a list of lookup records.")
        raw_cards = []
    for card in raw_cards:
        if isinstance(card, dict) and text(card.get("card_id")):
            cards_by_id[text(card["card_id"])] = card

    selected = payload.get("selected_debit_card_ids", [])
    if not isinstance(selected, list):
        add_blocker(blockers, "debit", "", "invalid_selection",
                    "selected_debit_card_ids must be a list.")
        selected = []
    if not selected:
        add_blocker(blockers, "debit", "", "no_debit_cards_selected",
                    "No specifically selected debit card is available to freeze.")

    confirmation = payload.get("freeze_confirmed") is True
    seen = set()
    for raw_id in selected:
        card_id = text(raw_id)
        if not card_id or card_id in seen:
            if card_id:
                add_blocker(blockers, "debit", card_id, "duplicate_selection",
                            "A card may be selected only once.")
            continue
        seen.add(card_id)
        card = cards_by_id.get(card_id)
        if card is None:
            add_blocker(blockers, "debit", card_id, "card_not_found",
                        "The selected card was not present in the supplied debit lookup.")
            continue
        if text(card.get("user_id")) != user_id:
            add_blocker(blockers, "debit", card_id, "ownership_mismatch",
                        "The debit-card holder does not match the verified user.")
            continue
        if text(card.get("account_id")) == "":
            add_blocker(blockers, "debit", card_id, "missing_linked_account",
                        "The debit lookup did not provide a linked checking account.")
            continue
        if text(card.get("status")).upper() != "ACTIVE":
            add_blocker(blockers, "debit", card_id, "card_not_active",
                        "Only an ACTIVE debit card is eligible for a temporary freeze.")
            continue
        if not verified or not user_id:
            continue
        if not confirmation:
            add_blocker(blockers, "debit", card_id, "freeze_not_confirmed",
                        "Obtain explicit confirmation after the freeze effects are explained.")
            continue
        freeze_actions.append({"tool": "freeze_debit_card_3892", "card_id": card_id})

    replacements = payload.get("credit_replacements", [])
    if replacements is None:
        replacements = []
    if not isinstance(replacements, list):
        add_blocker(blockers, "credit", "", "invalid_credit_replacements",
                    "credit_replacements must be a list.")
        replacements = []

    for item in replacements:
        if not isinstance(item, dict):
            add_blocker(blockers, "credit", "", "invalid_replacement_record",
                        "Each credit replacement must be an object.")
            continue
        account_id = text(item.get("account_id"))
        if not account_id:
            add_blocker(blockers, "credit", "", "missing_credit_account_id",
                        "A looked-up credit account identifier is required.")
            continue
        if not verified or not user_id:
            continue
        if text(item.get("user_id")) != user_id:
            add_blocker(blockers, "credit", account_id, "ownership_mismatch",
                        "The credit-card account holder does not match the verified user.")
            continue
        if item.get("customer_confirmed") is not True:
            add_blocker(blockers, "credit", account_id, "replacement_not_confirmed",
                        "Do not order a replacement without affirmative customer approval.")
            continue
        if item.get("eligibility_confirmed") is not True:
            add_blocker(blockers, "credit", account_id, "eligibility_not_confirmed",
                        "Confirm replacement eligibility before unlocking the ordering tool.")
            continue
        reason = text(item.get("reason"))
        if reason not in VALID_REASONS:
            add_blocker(blockers, "credit", account_id, "invalid_reason",
                        "Replacement reason must be one of the documented values.")
            continue
        address = text(item.get("shipping_address"))
        if not address:
            add_blocker(blockers, "credit", account_id, "shipping_address_unconfirmed",
                        "A confirmed complete shipping address is required.")
            continue
        speed = text(item.get("shipping_speed")).lower()
        if speed not in {"standard", "expedited"}:
            add_blocker(blockers, "credit", account_id, "invalid_shipping_speed",
                        "Shipping speed must be standard or expedited.")
            continue
        fee = fee_for(item.get("card_type"), speed)
        if speed == "expedited" and fee is None:
            add_blocker(blockers, "credit", account_id, "expedited_fee_unknown",
                        "Confirm the expedited fee for this card tier before ordering.")
            continue
        if speed == "expedited" and fee > 0 and item.get("fee_acknowledged") is not True:
            add_blocker(blockers, "credit", account_id, "expedited_fee_not_acknowledged",
                        "Customer acknowledgement is required for the expedited fee.")
            continue
        replacement_actions.append({
            "unlock_tool": "order_replacement_credit_card_7291",
            "call_tool": "order_replacement_credit_card_7291",
            "arguments": {
                "account_id": account_id,
                "reason": reason,
                "shipping_address": address,
                "shipping_speed": speed,
                "expedited_fee_acknowledgement": item.get("fee_acknowledged") is True,
                "notes": text(item.get("notes")),
            },
            "quoted_expedited_fee": fee if speed == "expedited" else 0,
        })

    return {
        "freeze_actions": freeze_actions,
        "replacement_actions": replacement_actions,
        "blockers": blockers,
        "ready": not blockers and bool(freeze_actions or replacement_actions),
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("Top-level JSON value must be an object.")
        print(json.dumps(main(incoming), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"freeze_actions": [], "replacement_actions": [], "blockers": [{
            "scope": "input", "identifier": "", "code": "invalid_input", "message": str(exc)
        }], "ready": False}, sort_keys=True))
