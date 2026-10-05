#!/usr/bin/env python3
"""Validate a file_credit_card_transaction_dispute_4829 payload.

Reads a JSON object from stdin and emits JSON: {"valid": bool, "errors": [str]}.
The script validates required field presence, permitted enums, Boolean fields,
date format, last-four format, and the partial-refund dependency. It does not
perform customer lookup, identity verification, or provisional-credit policy
calculation.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"
REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
REQUIRED = [
    "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
    "phone", "email", "address", "contacted_merchant", "purchase_date",
    "issue_noticed_date", "dispute_reason", "resolution_requested",
    "eligible_for_provisional_credit",
]


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, DATE_FORMAT)
        return True
    except ValueError:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc}"]}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"valid": False, "errors": ["payload must be a JSON object"]}))
        return

    errors = []
    for key in REQUIRED:
        if key not in payload or payload[key] is None or payload[key] == "":
            errors.append(f"missing required field: {key}")
    if errors:
        print(json.dumps({"valid": False, "errors": errors}, sort_keys=True))
        return

    for key in ("transaction_id", "full_name", "user_id", "phone", "email", "address"):
        if not isinstance(payload[key], str):
            errors.append(f"{key} must be a string")
    if payload["card_action"] not in ACTIONS:
        errors.append("card_action is not an allowed value")
    if not isinstance(payload["card_last_4_digits"], str) or not re.fullmatch(r"\d{4}", payload["card_last_4_digits"]):
        errors.append("card_last_4_digits must be exactly four digits")
    for key in ("contacted_merchant", "eligible_for_provisional_credit"):
        if not isinstance(payload[key], bool):
            errors.append(f"{key} must be boolean")
    for key in ("purchase_date", "issue_noticed_date"):
        if not valid_date(payload[key]):
            errors.append(f"{key} must be a real MM/DD/YYYY date")
    if payload["dispute_reason"] not in REASONS:
        errors.append("dispute_reason is not an allowed value")
    resolution = payload["resolution_requested"]
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not an allowed value")

    has_partial_amount = "partial_refund_amount" in payload and payload["partial_refund_amount"] is not None
    if resolution == "partial_refund":
        if not has_partial_amount:
            errors.append("partial_refund_amount is required for partial_refund")
        else:
            try:
                amount = Decimal(str(payload["partial_refund_amount"]))
                if not amount.is_finite() or amount <= 0:
                    errors.append("partial_refund_amount must be a positive number")
            except (InvalidOperation, ValueError):
                errors.append("partial_refund_amount must be a positive number")
    elif has_partial_amount:
        errors.append("partial_refund_amount is only allowed for partial_refund")

    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))


if __name__ == "__main__":
    main()
