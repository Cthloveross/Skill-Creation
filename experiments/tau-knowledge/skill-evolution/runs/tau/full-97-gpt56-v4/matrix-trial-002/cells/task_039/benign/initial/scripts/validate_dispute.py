#!/usr/bin/env python3
"""Validate a proposed credit-card dispute filing payload from JSON stdin."""
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
REQUIRED = ["transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
            "phone", "email", "address", "contacted_merchant", "purchase_date",
            "issue_noticed_date", "dispute_reason", "resolution_requested",
            "eligible_for_provisional_credit"]

def valid_date(value):
    try:
        dt.datetime.strptime(value, "%m/%d/%Y")
        return True
    except (ValueError, TypeError):
        return False

def decimal_value(value):
    if isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value).replace("$", "").replace(",", ""))

def main(p):
    errors = []
    for key in REQUIRED:
        if key not in p or p[key] is None or (isinstance(p[key], str) and not p[key].strip()):
            errors.append(f"missing_{key}")
    if p.get("card_action") not in ACTIONS:
        errors.append("invalid_card_action")
    digits = p.get("card_last_4_digits")
    if not isinstance(digits, str) or not re.fullmatch(r"\d{4}", digits):
        errors.append("card_last_4_digits_must_be_four_digits")
    if not isinstance(p.get("contacted_merchant"), bool):
        errors.append("contacted_merchant_must_be_boolean")
    if not isinstance(p.get("eligible_for_provisional_credit"), bool):
        errors.append("eligible_for_provisional_credit_must_be_boolean")
    for key in ("purchase_date", "issue_noticed_date"):
        if key in p and not valid_date(p[key]):
            errors.append(f"{key}_must_be_MM_DD_YYYY")
    if p.get("dispute_reason") not in REASONS:
        errors.append("invalid_dispute_reason")
    resolution = p.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("invalid_resolution_requested")
    partial = p.get("partial_refund_amount")
    if resolution == "partial_refund":
        try:
            amount = decimal_value(partial)
            if amount <= 0:
                errors.append("partial_refund_amount_must_be_positive")
            if "transaction_amount" in p and amount > decimal_value(p["transaction_amount"]):
                errors.append("partial_refund_amount_exceeds_transaction_amount")
        except (InvalidOperation, ValueError, TypeError):
            errors.append("partial_refund_amount_must_be_a_positive_number")
    elif partial is not None:
        errors.append("partial_refund_amount_only_allowed_for_partial_refund")
    return {"valid": not errors, "errors": errors}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload)))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}))
        sys.exit(1)
