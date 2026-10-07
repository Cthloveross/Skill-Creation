#!/usr/bin/env python3
"""Validate the exact JSON payload for file_credit_card_transaction_dispute_4829.

Read one JSON object from stdin. On success write
{"valid":true,"payload":<original object>}; on failure write
{"valid":false,"errors":[...]} and exit 2. This performs no bank action.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
CARD_ACTIONS = {"keep_active", "cancel_and_reissue"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
REQUIRED = {
    "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
    "phone", "email", "address", "contacted_merchant", "purchase_date",
    "issue_noticed_date", "dispute_reason", "resolution_requested",
    "eligible_for_provisional_credit",
}
OPTIONAL = {"partial_refund_amount"}


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%m/%d/%Y")
        return True
    except ValueError:
        return False


def positive_number(value):
    # bool is a subclass of int, but is not an acceptable monetary amount.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return decimal_value.is_finite() and decimal_value > 0


def validate(payload):
    if not isinstance(payload, dict):
        return ["payload must be a JSON object"]
    errors = []
    missing = REQUIRED - payload.keys()
    if missing:
        errors.append("missing required fields: " + ", ".join(sorted(missing)))
    unknown = payload.keys() - REQUIRED - OPTIONAL
    if unknown:
        errors.append("unsupported fields: " + ", ".join(sorted(unknown)))
    for field in ("transaction_id", "full_name", "user_id", "phone", "email", "address"):
        if field in payload and not nonempty_string(payload[field]):
            errors.append(field + " must be a nonempty string")
    if "card_action" in payload and payload["card_action"] not in CARD_ACTIONS:
        errors.append("card_action is not permitted")
    if "card_last_4_digits" in payload and (
        not isinstance(payload["card_last_4_digits"], str)
        or re.fullmatch(r"\d{4}", payload["card_last_4_digits"]) is None
    ):
        errors.append("card_last_4_digits must be exactly four digits")
    for field in ("purchase_date", "issue_noticed_date"):
        if field in payload and not valid_date(payload[field]):
            errors.append(field + " must use MM/DD/YYYY")
    if "contacted_merchant" in payload and not isinstance(payload["contacted_merchant"], bool):
        errors.append("contacted_merchant must be boolean")
    if "eligible_for_provisional_credit" in payload and not isinstance(payload["eligible_for_provisional_credit"], bool):
        errors.append("eligible_for_provisional_credit must be boolean")
    if "dispute_reason" in payload and payload["dispute_reason"] not in REASONS:
        errors.append("dispute_reason is not permitted")
    resolution = payload.get("resolution_requested")
    if resolution is not None and resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not permitted")
    has_partial = "partial_refund_amount" in payload
    if resolution == "partial_refund":
        if not has_partial:
            errors.append("partial_refund_amount is required for partial_refund")
        elif not positive_number(payload["partial_refund_amount"]):
            errors.append("partial_refund_amount must be a positive finite number")
    elif has_partial:
        errors.append("partial_refund_amount is allowed only for partial_refund")
    return errors


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": ["invalid JSON: " + str(exc)]}, separators=(",", ":")))
        return 2
    errors = validate(payload)
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, separators=(",", ":")))
        return 2
    print(json.dumps({"valid": True, "payload": payload}, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
