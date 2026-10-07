#!/usr/bin/env python3
"""Validate the structural schema for one credit-card dispute filing.

Reads {"dispute": {...}} from stdin and writes {"valid": bool, "errors": [str]}.
This helper is intentionally local/schema-only and does not execute any bank action.
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
ACTIONS = {"keep_active", "cancel_and_reissue"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
REQUIRED_STRINGS = (
    "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
    "phone", "email", "address", "purchase_date", "issue_noticed_date",
    "dispute_reason", "resolution_requested",
)


def valid_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%m/%d/%Y")
        return True
    except ValueError:
        return False


def main():
    try:
        root = json.load(sys.stdin)
        d = root["dispute"]
        if not isinstance(d, dict):
            raise ValueError("dispute must be an object")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}))
        return

    errors = []
    for field in REQUIRED_STRINGS:
        if not isinstance(d.get(field), str) or not d[field].strip():
            errors.append(field + " must be a nonempty string")
    if d.get("card_action") not in ACTIONS:
        errors.append("card_action is invalid")
    if not isinstance(d.get("card_last_4_digits"), str) or not re.fullmatch(r"\d{4}", d.get("card_last_4_digits", "")):
        errors.append("card_last_4_digits must be exactly four digits")
    if type(d.get("contacted_merchant")) is not bool:
        errors.append("contacted_merchant must be boolean")
    if type(d.get("eligible_for_provisional_credit")) is not bool:
        errors.append("eligible_for_provisional_credit must be boolean")
    for field in ("purchase_date", "issue_noticed_date"):
        if not valid_date(d.get(field)):
            errors.append(field + " must use MM/DD/YYYY")
    if d.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is invalid")
    resolution = d.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is invalid")
    has_partial = "partial_refund_amount" in d
    if resolution == "partial_refund":
        if not has_partial or type(d.get("partial_refund_amount")) is bool:
            errors.append("partial_refund_amount is required for partial_refund")
        else:
            try:
                value = Decimal(str(d["partial_refund_amount"]))
                if not value.is_finite() or value <= 0:
                    errors.append("partial_refund_amount must be a positive finite number")
            except (InvalidOperation, ValueError):
                errors.append("partial_refund_amount must be a positive finite number")
    elif has_partial:
        errors.append("partial_refund_amount is allowed only for partial_refund")
    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))


if __name__ == "__main__":
    main()
