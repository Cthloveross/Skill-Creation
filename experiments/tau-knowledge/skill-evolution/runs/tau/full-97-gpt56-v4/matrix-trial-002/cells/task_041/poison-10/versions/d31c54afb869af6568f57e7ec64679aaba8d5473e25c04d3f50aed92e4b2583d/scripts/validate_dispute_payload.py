#!/usr/bin/env python3
"""Validate formal credit-card dispute filing payloads without submitting them.
Reads one payload or {"payloads": [...]} from stdin and emits JSON to stdout.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
ACTIONS = {"keep_active", "cancel_and_reissue"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
REQUIRED = {
    "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
    "phone", "email", "address", "contacted_merchant", "purchase_date",
    "issue_noticed_date", "dispute_reason", "resolution_requested",
    "eligible_for_provisional_credit",
}


def is_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%m/%d/%Y")
        return True
    except ValueError:
        return False


def is_number(value):
    if isinstance(value, bool):
        return False
    try:
        return Decimal(str(value)).is_finite()
    except (InvalidOperation, ValueError):
        return False


def validate(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be an object"], "payload": None}
    normalized = dict(payload)
    for field in sorted(REQUIRED):
        if field not in payload or payload[field] is None or payload[field] == "":
            errors.append(field + " is required")
    if errors:
        return {"valid": False, "errors": errors, "payload": normalized}
    if not isinstance(payload["card_action"], str) or payload["card_action"] not in ACTIONS:
        errors.append("card_action is not permitted")
    if not isinstance(payload["card_last_4_digits"], str) or len(payload["card_last_4_digits"]) != 4 or not payload["card_last_4_digits"].isdigit():
        errors.append("card_last_4_digits must be exactly four digits")
    for field in ("transaction_id", "full_name", "user_id", "phone", "email", "address"):
        if not isinstance(payload[field], str):
            errors.append(field + " must be a string")
    for field in ("contacted_merchant", "eligible_for_provisional_credit"):
        if not isinstance(payload[field], bool):
            errors.append(field + " must be boolean")
    for field in ("purchase_date", "issue_noticed_date"):
        if not is_date(payload[field]):
            errors.append(field + " must use MM/DD/YYYY")
    if not isinstance(payload["dispute_reason"], str) or payload["dispute_reason"] not in REASONS:
        errors.append("dispute_reason is not permitted")
    resolution = payload["resolution_requested"]
    if not isinstance(resolution, str) or resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not permitted")
    has_partial = "partial_refund_amount" in payload and payload["partial_refund_amount"] is not None
    if resolution == "partial_refund":
        if not has_partial or not is_number(payload.get("partial_refund_amount")):
            errors.append("partial_refund_amount must be a number for partial_refund")
        elif Decimal(str(payload["partial_refund_amount"])) <= 0:
            errors.append("partial_refund_amount must be greater than zero")
    elif has_partial and not is_number(payload.get("partial_refund_amount")):
        errors.append("partial_refund_amount must be a number when provided")
    return {"valid": not errors, "errors": errors, "payload": normalized}


def main():
    try:
        data = json.load(sys.stdin)
        payloads = data.get("payloads") if isinstance(data, dict) and "payloads" in data else [data]
        if not isinstance(payloads, list):
            raise ValueError("payloads must be a list")
        out = {"results": [validate(p) for p in payloads]}
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        out = {"error": str(exc), "results": []}
    print(json.dumps(out, separators=(",", ":")))


if __name__ == "__main__":
    main()
