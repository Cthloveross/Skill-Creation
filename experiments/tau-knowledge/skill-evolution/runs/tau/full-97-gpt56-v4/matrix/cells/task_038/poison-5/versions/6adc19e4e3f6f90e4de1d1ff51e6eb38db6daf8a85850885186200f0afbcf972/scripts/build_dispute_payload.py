#!/usr/bin/env python3
"""Validate and prepare one dispute-tool argument object from JSON stdin."""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {"unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount", "goods_services_not_received", "goods_services_not_as_described", "canceled_subscription_still_charging", "refund_never_processed"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
REQUIRED = ("transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id", "phone", "email", "address", "contacted_merchant", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested")


def valid_date(value):
    try:
        return isinstance(value, str) and datetime.strptime(value, "%m/%d/%Y").strftime("%m/%d/%Y") == value
    except ValueError:
        return False


def main():
    try:
        source = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "payload": None, "errors": ["invalid JSON: " + str(exc)]}))
        return
    dispute = source.get("dispute") if isinstance(source, dict) else None
    decision = source.get("provisional_decision") if isinstance(source, dict) else None
    errors = []
    if not isinstance(dispute, dict):
        print(json.dumps({"ok": False, "payload": None, "errors": ["dispute must be an object"]}))
        return
    for field in REQUIRED:
        if field not in dispute or dispute[field] is None or (isinstance(dispute[field], str) and not dispute[field].strip()):
            errors.append("missing " + field)
    if dispute.get("card_action") not in ACTIONS:
        errors.append("invalid card_action")
    if not re.fullmatch(r"\d{4}", str(dispute.get("card_last_4_digits", ""))):
        errors.append("card_last_4_digits must contain exactly four digits")
    if not isinstance(dispute.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    if not valid_date(dispute.get("purchase_date")):
        errors.append("purchase_date must be MM/DD/YYYY")
    if not valid_date(dispute.get("issue_noticed_date")):
        errors.append("issue_noticed_date must be MM/DD/YYYY")
    if dispute.get("dispute_reason") not in REASONS:
        errors.append("invalid dispute_reason")
    resolution = dispute.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("invalid resolution_requested")
    partial = dispute.get("partial_refund_amount")
    if resolution == "partial_refund":
        try:
            if Decimal(str(partial)) <= 0:
                raise InvalidOperation
        except (InvalidOperation, ValueError, TypeError):
            errors.append("partial_refund_amount must be a positive number for partial_refund")
    elif partial is not None:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")
    if decision not in {"eligible", "ineligible"}:
        errors.append("provisional_decision must be eligible or ineligible")
    if errors:
        print(json.dumps({"ok": False, "payload": None, "errors": errors}))
        return
    payload = {key: dispute[key] for key in REQUIRED}
    payload["eligible_for_provisional_credit"] = decision == "eligible"
    if resolution == "partial_refund":
        payload["partial_refund_amount"] = float(Decimal(str(partial)))
    print(json.dumps({"ok": True, "payload": payload, "errors": []}))


if __name__ == "__main__":
    main()
