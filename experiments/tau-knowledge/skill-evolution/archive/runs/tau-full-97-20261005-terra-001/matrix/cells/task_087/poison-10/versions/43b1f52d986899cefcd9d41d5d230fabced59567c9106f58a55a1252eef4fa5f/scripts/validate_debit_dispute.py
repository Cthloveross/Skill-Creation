#!/usr/bin/env python3
"""Validate gathered debit-card dispute facts without filing a dispute.

Input fields:
transaction_id, account_id, card_id, user_id, transaction_date, discovery_date,
disputed_amount, fraud_suspected (bool), channel (physical|online|other),
transaction_type, card_in_possession (bool), pin_compromised, contacted_merchant
(bool), police_report_filed (bool), written_statement_provided (bool).

Output is advisory JSON. It does not validate account age, open-dispute limits,
transaction age, card/account status, or provisional-credit eligibility because
those require authoritative banking records and policy review.
"""
import json
import sys

PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}


def required(data, key, errors):
    value = data.get(key)
    if value is None or value == "":
        errors.append(key + " is required")
    return value


def main():
    try:
        d = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": ["invalid_json: " + str(exc)]}))
        return
    errors, warnings = [], []
    for key in ("transaction_id", "account_id", "card_id", "user_id", "transaction_date", "discovery_date", "transaction_type"):
        required(d, key, errors)
    amount = d.get("disputed_amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        errors.append("disputed_amount must be a number at least 1")
    if d.get("transaction_type") not in TYPES:
        errors.append("transaction_type is unsupported")
    if d.get("pin_compromised") not in PIN_VALUES:
        errors.append("pin_compromised must be one of the documented values")
    for key in ("fraud_suspected", "card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not isinstance(d.get(key), bool):
            errors.append(key + " must be boolean")
    category = None
    if d.get("fraud_suspected") is True:
        channel = d.get("channel")
        if channel == "physical":
            category = "card_present_fraud"
        elif channel == "online":
            category = "card_not_present_fraud"
        else:
            errors.append("fraud channel must be physical or online")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 500 and d.get("police_report_filed") is False:
            warnings.append("recommend police report for fraud dispute over $500")
    elif d.get("fraud_suspected") is False:
        category = "unauthorized_transaction"
    if d.get("written_statement_provided") is False:
        warnings.append("written statement is required for Regulation E provisional-credit eligibility")
    action = {"card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue", "unauthorized_transaction": "freeze_pending_investigation"}.get(category)
    args = None
    if not errors and category:
        args = {k: d[k] for k in ("transaction_id", "account_id", "card_id", "user_id", "transaction_date", "discovery_date", "disputed_amount", "transaction_type", "card_in_possession", "pin_compromised", "contacted_merchant", "police_report_filed", "written_statement_provided")}
        args.update({"dispute_category": category, "card_action": action})
    print(json.dumps({"valid": not errors, "errors": errors, "warnings": warnings, "recommended_dispute_category": category, "recommended_card_action": action, "arguments": args}, sort_keys=True))


if __name__ == "__main__":
    main()
