#!/usr/bin/env python3
"""Validate the formal credit-card dispute filing payload from JSON stdin."""
import json
import re
import sys
from datetime import datetime

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}


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
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"valid": False, "errors": ["payload must be a JSON object"]}))
        return

    errors = []
    for field in ("transaction_id", "full_name", "user_id", "phone", "email", "address"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            errors.append(f"{field} must be a non-empty string")

    if data.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    if not isinstance(data.get("card_last_4_digits"), str) or not re.fullmatch(r"\d{4}", data["card_last_4_digits"]):
        errors.append("card_last_4_digits must contain exactly four digits")
    for field in ("contacted_merchant", "eligible_for_provisional_credit"):
        if not isinstance(data.get(field), bool):
            errors.append(f"{field} must be boolean")
    for field in ("purchase_date", "issue_noticed_date"):
        if not valid_date(data.get(field)):
            errors.append(f"{field} must use MM/DD/YYYY format")
    if data.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not permitted")
    resolution = data.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not permitted")
    has_partial = "partial_refund_amount" in data and data.get("partial_refund_amount") is not None
    if resolution == "partial_refund":
        try:
            raw_partial = data.get("partial_refund_amount")
            if isinstance(raw_partial, bool):
                raise ValueError
            partial = float(raw_partial)
            if partial <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append("partial_refund_amount must be a positive number for partial_refund")
    elif has_partial:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")

    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))


if __name__ == "__main__":
    main()
