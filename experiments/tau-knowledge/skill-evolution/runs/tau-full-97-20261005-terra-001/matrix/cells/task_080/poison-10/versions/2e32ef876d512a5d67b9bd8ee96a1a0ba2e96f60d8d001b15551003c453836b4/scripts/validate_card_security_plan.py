#!/usr/bin/env python3
"""Validate proposed debit freeze/unfreeze and credit replacement actions.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
uses only supplied data; it never calls banking tools or changes bank state.
"""

import json
import sys

VALID_REASONS = {
    "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"
}
ENTRY = {"bronze rewards", "bronze rewards card", "ecocard", "business bronze", "business bronze rewards card"}
MID = {"silver rewards", "silver rewards card", "business silver", "business silver rewards card", "green rewards", "green rewards card", "silver zoom", "silver zoom card"}
PREMIUM = {"gold", "gold rewards", "gold rewards card", "business gold", "business gold rewards card", "platinum", "platinum rewards card", "business platinum rewards card", "diamond elite", "diamond elite card"}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def add(blockers, scope, identifier, code, message):
    blockers.append({"scope": scope, "identifier": identifier, "code": code, "message": message})


def list_value(payload, key, blockers, scope):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        add(blockers, scope, "", "invalid_" + key, key + " must be a list.")
        return []
    return value


def expedited_fee(card_type, speed):
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


def unique_ids(values, blockers, scope, empty_code):
    output, seen = [], set()
    for value in values:
        identifier = text(value)
        if not identifier:
            add(blockers, scope, "", empty_code, "Each selected card identifier must be nonempty.")
        elif identifier in seen:
            add(blockers, scope, identifier, "duplicate_selection", "A card may be selected only once per action type.")
        else:
            seen.add(identifier)
            output.append(identifier)
    return output


def main(payload):
    blockers = []
    freeze_actions = []
    unfreeze_actions = []
    replacement_actions = []
    user_id = text(payload.get("user_id"))
    verified = payload.get("verified") is True

    if not user_id:
        add(blockers, "session", "", "missing_user_id", "A verified user_id is required.")
    if not verified:
        add(blockers, "session", user_id, "identity_not_verified", "Do not dispatch banking actions before successful identity verification.")

    cards = {}
    for record in list_value(payload, "debit_cards", blockers, "debit"):
        if not isinstance(record, dict):
            add(blockers, "debit", "", "invalid_debit_card_record", "Each debit-card lookup record must be an object.")
            continue
        card_id = text(record.get("card_id"))
        if not card_id:
            add(blockers, "debit", "", "missing_card_id", "A debit-card lookup record requires card_id.")
        elif card_id in cards:
            add(blockers, "debit", card_id, "duplicate_card_record", "Card lookup contains duplicate card_id values.")
        else:
            cards[card_id] = record

    accounts = {}
    for record in list_value(payload, "checking_accounts", blockers, "account"):
        if not isinstance(record, dict):
            add(blockers, "account", "", "invalid_checking_account_record", "Each checking-account record must be an object.")
            continue
        account_id = text(record.get("account_id"))
        if not account_id:
            add(blockers, "account", "", "missing_account_id", "A checking-account record requires account_id.")
        else:
            accounts[account_id] = record

    selected_freezes = unique_ids(
        list_value(payload, "selected_debit_card_ids", blockers, "debit"),
        blockers, "debit", "missing_freeze_card_id"
    )
    if not selected_freezes:
        add(blockers, "debit", "", "no_debit_cards_selected", "No specifically selected debit card is available to freeze.")
    freeze_confirmed = payload.get("freeze_confirmed") is True

    for card_id in selected_freezes:
        card = cards.get(card_id)
        if card is None:
            add(blockers, "debit", card_id, "card_not_found", "The selected card was absent from supplied debit lookup data.")
        elif text(card.get("user_id")) != user_id:
            add(blockers, "debit", card_id, "ownership_mismatch", "The debit-card holder does not match the verified user.")
        elif not text(card.get("account_id")):
            add(blockers, "debit", card_id, "missing_linked_account", "The debit card lacks a linked checking account.")
        elif text(card.get("status")).upper() != "ACTIVE":
            add(blockers, "debit", card_id, "card_not_active", "Only an ACTIVE debit card is eligible for temporary freeze.")
        elif not freeze_confirmed:
            add(blockers, "debit", card_id, "freeze_not_confirmed", "Obtain explicit freeze confirmation after explaining its effects.")
        elif verified and user_id:
            freeze_actions.append({"tool": "freeze_debit_card_3892", "card_id": card_id})

    requested_unfreezes = unique_ids(
        list_value(payload, "requested_unfreeze_card_ids", blockers, "debit"),
        blockers, "debit", "missing_unfreeze_card_id"
    )
    for card_id in requested_unfreezes:
        card = cards.get(card_id)
        if card is None:
            add(blockers, "debit", card_id, "card_not_found", "The requested card was absent from supplied debit lookup data.")
            continue
        if text(card.get("user_id")) != user_id:
            add(blockers, "debit", card_id, "ownership_mismatch", "The debit-card holder does not match the verified user.")
            continue
        account_id = text(card.get("account_id"))
        if not account_id:
            add(blockers, "debit", card_id, "missing_linked_account", "The debit card lacks a linked checking account.")
            continue
        if text(card.get("status")).upper() != "FROZEN":
            add(blockers, "debit", card_id, "card_not_frozen", "Only a FROZEN debit card is eligible for unfreeze.")
            continue
        account = accounts.get(account_id)
        if account is None:
            add(blockers, "debit", card_id, "linked_account_not_checked", "Look up the linked checking account and confirm it is OPEN before unfreezing.")
            continue
        if text(account.get("user_id")) and text(account.get("user_id")) != user_id:
            add(blockers, "debit", card_id, "linked_account_ownership_mismatch", "The linked checking account does not match the verified user.")
            continue
        if text(account.get("status")).upper() != "OPEN":
            add(blockers, "debit", card_id, "linked_account_not_open", "The linked checking account must be OPEN before unfreezing.")
            continue
        if verified and user_id:
            unfreeze_actions.append({"tool": "unfreeze_debit_card_3893", "card_id": card_id})

    for item in list_value(payload, "credit_replacements", blockers, "credit"):
        if not isinstance(item, dict):
            add(blockers, "credit", "", "invalid_replacement_record", "Each credit replacement must be an object.")
            continue
        account_id = text(item.get("account_id"))
        if not account_id:
            add(blockers, "credit", "", "missing_credit_account_id", "A looked-up credit account identifier is required.")
            continue
        if text(item.get("user_id")) != user_id:
            add(blockers, "credit", account_id, "ownership_mismatch", "The credit-card account holder does not match the verified user.")
            continue
        if item.get("customer_confirmed") is not True:
            add(blockers, "credit", account_id, "replacement_not_confirmed", "Do not order a replacement without affirmative customer approval.")
            continue
        if item.get("eligibility_confirmed") is not True:
            add(blockers, "credit", account_id, "eligibility_not_confirmed", "Confirm replacement eligibility before unlocking the ordering tool.")
            continue
        reason = text(item.get("reason"))
        if reason not in VALID_REASONS:
            add(blockers, "credit", account_id, "invalid_reason", "Replacement reason is not documented.")
            continue
        address = text(item.get("shipping_address"))
        if not address:
            add(blockers, "credit", account_id, "shipping_address_unconfirmed", "A confirmed complete shipping address is required.")
            continue
        speed = text(item.get("shipping_speed")).lower()
        if speed not in {"standard", "expedited"}:
            add(blockers, "credit", account_id, "invalid_shipping_speed", "Shipping speed must be standard or expedited.")
            continue
        fee = expedited_fee(item.get("card_type"), speed)
        if fee is None:
            add(blockers, "credit", account_id, "expedited_fee_unknown", "Confirm the expedited fee for this card tier before ordering.")
            continue
        if speed == "expedited" and fee > 0 and item.get("fee_acknowledged") is not True:
            add(blockers, "credit", account_id, "expedited_fee_not_acknowledged", "Customer acknowledgement is required for the expedited fee.")
            continue
        if verified and user_id:
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
        "unfreeze_actions": unfreeze_actions,
        "replacement_actions": replacement_actions,
        "blockers": blockers,
        "ready": not blockers and bool(freeze_actions or unfreeze_actions or replacement_actions),
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("Top-level JSON value must be an object.")
        print(json.dumps(main(incoming), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "freeze_actions": [], "unfreeze_actions": [], "replacement_actions": [],
            "blockers": [{"scope": "input", "identifier": "", "code": "invalid_input", "message": str(exc)}],
            "ready": False,
        }, sort_keys=True))
