#!/usr/bin/env python3
"""Validate structured preconditions for lost-wallet card protection.

Reads a JSON object from stdin and emits a JSON object to stdout. This helper is
read-only: it never calls banking tools and never performs an action.
"""

import json
import sys

ALLOWED_REASONS = {
    "fraud_suspected", "lost", "stolen", "damaged", "expired", "other"
}
ALLOWED_SPEEDS = {"standard", "expedited"}


def as_list(value):
    return value if isinstance(value, list) else []


def text(value):
    return value if isinstance(value, str) else ""


def main(data):
    blockers = []
    user_id = text(data.get("user_id"))
    verified_fields = {text(v) for v in as_list(data.get("verified_fields"))}
    identity_ok = bool(user_id) and len(verified_fields & {
        "date_of_birth", "email", "phone_number", "address"
    }) >= 2
    if not identity_ok:
        blockers.append({
            "scope": "identity",
            "reason": "At least two matched profile fields and a user_id are required."
        })

    requested_ids = {text(v) for v in as_list(data.get("requested_account_ids")) if text(v)}
    if not requested_ids:
        blockers.append({
            "scope": "debit",
            "reason": "No uniquely identified requested checking account IDs were supplied."
        })

    checking_ids = set()
    for account in as_list(data.get("accounts")):
        if not isinstance(account, dict):
            continue
        account_id = text(account.get("account_id"))
        account_type = text(account.get("account_type")).upper()
        if account_id in requested_ids and account_type == "CHECKING":
            checking_ids.add(account_id)

    for account_id in sorted(requested_ids - checking_ids):
        blockers.append({
            "scope": "debit",
            "account_id": account_id,
            "reason": "Requested account was not confirmed as a returned checking account."
        })

    eligible = []
    seen = set()
    for card in as_list(data.get("debit_cards")):
        if not isinstance(card, dict):
            continue
        card_id = text(card.get("card_id"))
        account_id = text(card.get("account_id"))
        owner_id = text(card.get("user_id"))
        status = text(card.get("status")).upper()
        if account_id not in requested_ids:
            continue
        if not card_id:
            blockers.append({"scope": "debit", "reason": "A returned debit-card record has no card_id."})
        elif owner_id != user_id:
            blockers.append({
                "scope": "debit", "card_id": card_id,
                "reason": "Card ownership does not match the verified user."
            })
        elif account_id not in checking_ids:
            # The account blocker already explains why it cannot be used.
            continue
        elif status != "ACTIVE":
            blockers.append({
                "scope": "debit", "card_id": card_id,
                "reason": "Only an ACTIVE debit card can be frozen.", "status": status
            })
        elif card_id not in seen:
            eligible.append(card_id)
            seen.add(card_id)

    if identity_ok is False:
        eligible = []

    credit = data.get("credit_replacement")
    credit_ready = False
    if isinstance(credit, dict) and credit.get("requested") is True:
        reasons = []
        if not identity_ok:
            reasons.append("identity is not verified")
        if text(credit.get("account_user_id")) != user_id:
            reasons.append("credit-card ownership does not match the verified user")
        if text(credit.get("account_status")).upper() != "ACTIVE":
            reasons.append("selected credit-card account is not ACTIVE")
        if credit.get("eligibility_confirmed") is not True:
            reasons.append("replacement eligibility has not been confirmed")
        if text(credit.get("reason")) not in ALLOWED_REASONS:
            reasons.append("replacement reason is missing or unsupported")
        if credit.get("shipping_address_confirmed") is not True:
            reasons.append("shipping address is not confirmed")
        speed = text(credit.get("shipping_speed"))
        if speed not in ALLOWED_SPEEDS:
            reasons.append("shipping speed is missing or unsupported")
        if speed == "expedited" and credit.get("expedited_fee_acknowledged") is not True:
            reasons.append("required expedited fee acknowledgement is missing")
        if reasons:
            blockers.append({"scope": "credit_replacement", "reason": "; ".join(reasons)})
        else:
            credit_ready = True

    return {
        "identity_verified": identity_ok,
        "freeze_card_ids": eligible,
        "credit_order_ready": credit_ready,
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
