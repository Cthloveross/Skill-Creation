#!/usr/bin/env python3
"""Validate the required structure for a credit-card dispute submission."""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"
CARD_ACTIONS = {"keep_active", "cancel_and_reissue"}
REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
REQUIRED = {
    "transaction_id": str, "card_action": str, "card_last_4_digits": str,
    "full_name": str, "user_id": str, "phone": str, "email": str,
    "address": str, "contacted_merchant": bool, "purchase_date": str,
    "issue_noticed_date": str, "dispute_reason": str,
    "resolution_requested": str, "eligible_for_provisional_credit": bool,
}


def date_ok(value):
    try:
        datetime.strptime(value, DATE_FORMAT)
        return True
    except (TypeError, ValueError):
        return False


def positive_number(value):
    if isinstance(value, bool):
        return False
    try:
        return Decimal(str(value)) > 0
    except (InvalidOperation, ValueError):
        return False


def main():
    try:
        envelope = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid input JSON: {exc.msg}"]}))
        return
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    if not isinstance(payload, dict):
        print(json.dumps({"valid": False, "errors": ["payload must be an object"]}))
        return

    errors = []
    for key, expected_type in REQUIRED.items():
        if key not in payload:
            errors.append(f"missing required field: {key}")
        elif type(payload[key]) is not expected_type:
            errors.append(f"{key} must be {expected_type.__name__}")
        elif expected_type is str and not payload[key].strip():
            errors.append(f"{key} cannot be empty")

    if isinstance(payload.get("card_action"), str) and payload["card_action"] not in CARD_ACTIONS:
        errors.append("invalid card_action")
    suffix = payload.get("card_last_4_digits")
    if isinstance(suffix, str) and (len(suffix) != 4 or not suffix.isdigit()):
        errors.append("card_last_4_digits must contain exactly four digits")
    for key in ("purchase_date", "issue_noticed_date"):
        if key in payload and isinstance(payload[key], str) and not date_ok(payload[key]):
            errors.append(f"{key} must be a valid MM/DD/YYYY date")
    if isinstance(payload.get("dispute_reason"), str) and payload["dispute_reason"] not in REASONS:
        errors.append("invalid dispute_reason")
    resolution = payload.get("resolution_requested")
    if isinstance(resolution, str) and resolution not in RESOLUTIONS:
        errors.append("invalid resolution_requested")
    has_partial = "partial_refund_amount" in payload
    if resolution == "partial_refund":
        if not has_partial:
            errors.append("partial_refund_amount is required for partial_refund")
        elif not positive_number(payload["partial_refund_amount"]):
            errors.append("partial_refund_amount must be a positive number")
    elif has_partial:
        errors.append("partial_refund_amount is only allowed for partial_refund")

    print(json.dumps({"valid": not errors, "errors": errors}))


if __name__ == "__main__":
    main()
