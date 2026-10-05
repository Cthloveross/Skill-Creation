#!/usr/bin/env python3
"""Assess verification and requested card-product matching from JSON stdin."""
import json
import re
import sys

IDENTITY_FIELDS = ("email", "phone_number", "address", "date_of_birth")


def text(value):
    return "" if value is None else str(value).strip()


def normalize(field, value):
    value = text(value)
    if field == "email":
        return value.casefold()
    if field == "phone_number":
        return "".join(re.findall(r"\d", value))
    if field == "address":
        return " ".join(value.casefold().split())
    if field == "date_of_birth":
        return value
    return value.casefold()


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("invalid JSON input: " + str(exc))
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    record = data.get("customer_record")
    confirmed = data.get("confirmed_identity", {})
    requested = text(data.get("requested_card_type"))
    accounts = data.get("accounts", [])
    if not isinstance(record, dict) or not text(record.get("user_id")):
        fail("customer_record with user_id is required")
    if not isinstance(confirmed, dict):
        fail("confirmed_identity must be an object")
    if not requested:
        fail("requested_card_type is required")
    if not isinstance(accounts, list):
        fail("accounts must be a list")

    verified = []
    supplied = []
    for field in IDENTITY_FIELDS:
        candidate = text(confirmed.get(field))
        expected = text(record.get(field))
        if candidate:
            supplied.append(field)
            if expected and normalize(field, candidate) == normalize(field, expected):
                verified.append(field)

    record_user_id = text(record["user_id"])
    requested_norm = requested.casefold()
    matches = []
    other_products = []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        if text(account.get("user_id")) != record_user_id:
            continue
        card_type = text(account.get("card_type"))
        if card_type.casefold() == requested_norm:
            matches.append(account)
        elif card_type:
            other_products.append(card_type)

    verification_complete = len(verified) >= 2
    if not verification_complete:
        decision = "need_identity_field"
        next_step = "Request another customer-confirmed identity field; do not disclose account information."
    elif len(matches) == 0:
        decision = "requested_card_absent"
        next_step = "State the requested card product was not found on the verified profile; do not substitute another card balance."
    elif len(matches) == 1:
        decision = "one_requested_card"
        next_step = "Log verification if not already logged, then disclose the matching account's current balance."
    else:
        decision = "multiple_requested_cards"
        next_step = "Ask the customer to identify the intended account before disclosing a balance."

    output = {
        "verified_fields": verified,
        "supplied_identity_fields": supplied,
        "verification_complete": verification_complete,
        "matching_account_count": len(matches),
        "matching_account_ids": [text(a.get("account_id")) for a in matches],
        "other_card_types_on_profile": sorted(set(other_products)),
        "decision": decision,
        "next_step": next_step,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
