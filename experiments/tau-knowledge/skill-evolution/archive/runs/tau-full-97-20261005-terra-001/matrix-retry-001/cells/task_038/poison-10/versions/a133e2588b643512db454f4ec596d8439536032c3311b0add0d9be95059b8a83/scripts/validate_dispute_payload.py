#!/usr/bin/env python3
"""Validate a file_credit_card_transaction_dispute_4829 payload.

Reads a JSON object from stdin and emits {"valid": bool, "errors": [string]}.
It validates structure only; it does not replace identity verification or policy
calculation.
"""
import json, re, sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REQUIRED = ("transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id", "phone", "email", "address", "contacted_merchant", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested", "eligible_for_provisional_credit")
ACTIONS = {"keep_active", "cancel_and_reissue"}
REASONS = {"unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount", "goods_services_not_received", "goods_services_not_as_described", "canceled_subscription_still_charging", "refund_never_processed"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
def is_date(v):
    try: return isinstance(v, str) and datetime.strptime(v, "%m/%d/%Y") is not None
    except ValueError: return False
def main():
    try: p = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc}"]})); return
    if not isinstance(p, dict): print(json.dumps({"valid": False, "errors": ["payload must be a JSON object"]})); return
    errors = [f"missing required field: {k}" for k in REQUIRED if k not in p or p[k] is None or p[k] == ""]
    if not errors:
        for k in ("transaction_id", "full_name", "user_id", "phone", "email", "address"):
            if not isinstance(p[k], str): errors.append(f"{k} must be a string")
        if p["card_action"] not in ACTIONS: errors.append("card_action is not an allowed value")
        if not isinstance(p["card_last_4_digits"], str) or not re.fullmatch(r"\d{4}", p["card_last_4_digits"]): errors.append("card_last_4_digits must be exactly four digits")
        for k in ("contacted_merchant", "eligible_for_provisional_credit"):
            if not isinstance(p[k], bool): errors.append(f"{k} must be boolean")
        for k in ("purchase_date", "issue_noticed_date"):
            if not is_date(p[k]): errors.append(f"{k} must be a real MM/DD/YYYY date")
        if p["dispute_reason"] not in REASONS: errors.append("dispute_reason is not an allowed value")
        resolution = p["resolution_requested"]
        if resolution not in RESOLUTIONS: errors.append("resolution_requested is not an allowed value")
        partial = p.get("partial_refund_amount")
        if resolution == "partial_refund":
            try:
                if partial is None or not Decimal(str(partial)).is_finite() or Decimal(str(partial)) <= 0: raise ValueError
            except (InvalidOperation, ValueError): errors.append("partial_refund_amount must be a positive number for partial_refund")
        elif partial is not None: errors.append("partial_refund_amount is only allowed for partial_refund")
    print(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
if __name__ == "__main__": main()
