#!/usr/bin/env python3
"""Read-only validation for lost-wallet card-protection facts.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not call tools, persist data, or perform banking actions.
"""

import json
import sys

ALLOWED_REASONS = {
    "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"
}
SECURITY_CLOSURE_REASONS = {"lost", "stolen", "fraud_suspected"}
ALLOWED_SPEEDS = {"standard", "expedited"}
IDENTITY_FIELDS = {"date_of_birth", "email", "phone_number", "address"}


def string(value):
    return value if isinstance(value, str) else ""


def records(value):
    return value if isinstance(value, list) else []


def string_set(value):
    return {string(item) for item in records(value) if string(item)}


def main(data):
    blockers = []
    user_id = string(data.get("user_id"))
    verified_fields = string_set(data.get("verified_fields"))
    identity_ok = bool(user_id) and len(verified_fields & IDENTITY_FIELDS) >= 2
    if not identity_ok:
        blockers.append({
            "scope": "identity",
            "reason": "A user_id and at least two matched profile fields are required."
        })

    requested_ids = string_set(data.get("requested_account_ids"))
    if not requested_ids:
        blockers.append({
            "scope": "debit",
            "reason": "No requested checking account IDs were supplied."
        })

    checking_ids = set()
    for account in records(data.get("accounts")):
        if not isinstance(account, dict):
            continue
        account_id = string(account.get("account_id"))
        account_type = string(account.get("account_type")).upper()
        if account_id in requested_ids and account_type == "CHECKING":
            checking_ids.add(account_id)

    for account_id in sorted(requested_ids - checking_ids):
        blockers.append({
            "scope": "debit",
            "account_id": account_id,
            "reason": "The requested account was not confirmed as a returned checking account."
        })

    freeze_ids = []
    seen = set()
    for card in records(data.get("debit_cards")):
        if not isinstance(card, dict):
            continue
        card_id = string(card.get("card_id"))
        account_id = string(card.get("account_id"))
        owner_id = string(card.get("user_id"))
        status = string(card.get("status")).upper()
        if account_id not in requested_ids:
            continue
        if not card_id:
            blockers.append({"scope": "debit", "reason": "A card record has no card_id."})
        elif account_id not in checking_ids:
            continue
        elif owner_id != user_id:
            blockers.append({
                "scope": "debit", "card_id": card_id,
                "reason": "Card ownership does not match the verified user."
            })
        elif status != "ACTIVE":
            blockers.append({
                "scope": "debit", "card_id": card_id,
                "status": status,
                "reason": "Only ACTIVE debit cards can be frozen."
            })
        elif card_id not in seen:
            seen.add(card_id)
            freeze_ids.append(card_id)

    if not identity_ok:
        freeze_ids = []

    credit_ready = False
    credit = data.get("credit_replacement")
    if isinstance(credit, dict) and credit.get("requested") is True:
        missing = []
        if not identity_ok:
            missing.append("identity is not verified")
        if not string(credit.get("account_id")):
            missing.append("selected credit-card account ID is missing")
        if string(credit.get("account_user_id")) != user_id:
            missing.append("credit-card ownership does not match the verified user")
        if string(credit.get("account_status")).upper() != "ACTIVE":
            missing.append("selected credit-card account is not ACTIVE")
        if string(credit.get("reason")) not in ALLOWED_REASONS:
            missing.append("replacement reason is missing or unsupported")
        if credit.get("shipping_address_confirmed") is not True:
            missing.append("shipping address is not confirmed")
        speed = string(credit.get("shipping_speed"))
        if speed not in ALLOWED_SPEEDS:
            missing.append("shipping speed is missing or unsupported")
        if speed == "expedited" and credit.get("expedited_fee_acknowledged") is not True:
            missing.append("applicable expedited fee acknowledgement is missing")
        if missing:
            blockers.append({
                "scope": "credit_replacement",
                "reason": "; ".join(missing)
            })
        else:
            credit_ready = True

    close_ids = []
    closure = data.get("confirmed_loss_closure")
    if isinstance(closure, dict) and closure.get("requested") is True:
        missing = []
        if not identity_ok:
            missing.append("identity is not verified")
        reason = string(closure.get("reason"))
        if reason not in SECURITY_CLOSURE_REASONS:
            missing.append("a loss, theft, or fraud_suspected closure reason is required")
        frozen_ids = string_set(closure.get("previously_frozen_card_ids"))
        if not frozen_ids:
            missing.append("no previously frozen card IDs were supplied")
        owned_ids = string_set(closure.get("ownership_confirmed_card_ids"))
        if frozen_ids - owned_ids:
            missing.append("ownership is not confirmed for every previously frozen card")
        if missing:
            blockers.append({
                "scope": "confirmed_loss_closure",
                "reason": "; ".join(missing)
            })
        else:
            close_ids = sorted(frozen_ids)

    return {
        "identity_verified": identity_ok,
        "freeze_card_ids": freeze_ids,
        "credit_order_ready": credit_ready,
        "close_card_ids": close_ids,
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON value must be an object.")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
