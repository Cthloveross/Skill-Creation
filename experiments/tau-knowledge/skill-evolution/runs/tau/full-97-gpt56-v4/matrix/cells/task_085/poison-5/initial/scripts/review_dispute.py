#!/usr/bin/env python3
"""Deterministic pre-filing review for debit-card dispute facts.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active",
    "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active",
    "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
QUALIFYING = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}

def date_value(value, name, errors):
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(f"{name} must use MM/DD/YYYY.")
        return None

def main(data):
    errors, warnings = [], []
    category = data.get("category")
    transaction_type = data.get("transaction_type")
    if category not in CATEGORIES:
        errors.append("A supported dispute category is required.")
    if transaction_type not in TYPES:
        errors.append("A supported transaction type is required.")
    if category == "atm_cash_discrepancy" and transaction_type != "atm_withdrawal":
        errors.append("ATM cash discrepancy must use transaction_type atm_withdrawal.")
    if category == "atm_deposit_not_credited" and transaction_type != "atm_deposit":
        errors.append("ATM deposit not credited must use transaction_type atm_deposit.")

    transaction_date = date_value(data.get("transaction_date"), "transaction_date", errors)
    filing_date = date_value(data.get("filing_date"), "filing_date", errors)
    statement_date = date_value(data.get("statement_date"), "statement_date", errors)
    discovery_date = date_value(data.get("discovery_date"), "discovery_date", errors)
    if transaction_date and filing_date:
        age = (filing_date - transaction_date).days
        if age < 0:
            errors.append("Filing date cannot precede transaction date.")
        elif age > 60:
            errors.append("Transaction is more than 60 days old.")
    elif not transaction_date or not filing_date:
        errors.append("Transaction and filing dates are required to validate the 60-day filing window.")
    if transaction_date and discovery_date and discovery_date < transaction_date:
        warnings.append("Discovery date precedes transaction date; verify the dates.")

    txn_amount = data.get("transaction_amount")
    disputed = data.get("disputed_amount")
    try:
        txn_abs = abs(float(txn_amount))
        disputed_num = float(disputed)
        if txn_abs < 1:
            errors.append("The transaction must be at least $1.00.")
        if disputed_num <= 0:
            errors.append("Disputed amount must be greater than zero.")
        if disputed_num > txn_abs:
            errors.append("Disputed amount cannot exceed the transaction amount.")
    except (TypeError, ValueError):
        errors.append("Transaction amount and disputed amount must be numeric.")

    if data.get("account_status") != "OPEN":
        errors.append("The linked checking account must be OPEN.")
    tier = data.get("account_tier")
    count = data.get("active_open_disputes")
    if tier not in LIMITS:
        errors.append("Account tier must be Entry, Mid, Premium, or Elite.")
    try:
        if tier in LIMITS and int(count) >= LIMITS[tier]:
            errors.append("The account has reached its maximum open-dispute limit.")
    except (TypeError, ValueError):
        errors.append("Active open-dispute count is required.")

    action = ACTIONS.get(category)
    pc = None
    required = ["statement_date", "discovery_date", "written_statement_provided",
                "account_status", "account_has_holds", "pin_compromised", "contacted_merchant"]
    if category in CATEGORIES and all(key in data for key in required) and statement_date and discovery_date:
        timely = (discovery_date - statement_date).days <= 60
        if (discovery_date - statement_date).days < 0:
            warnings.append("Discovery date precedes statement date; verify timely-reporting evidence.")
        pc = (timely and category in QUALIFYING and data.get("written_statement_provided") is True
              and data.get("account_status") == "OPEN" and data.get("account_has_holds") is False)
        if category not in QUALIFYING:
            pc = False
        if category not in {"card_present_fraud", "card_not_present_fraud"} and data.get("contacted_merchant") is False:
            pc = False
        if data.get("pin_compromised") == "yes_shared":
            pc = False
        opened = date_value(data.get("account_date_opened"), "account_date_opened", errors)
        if category == "card_not_present_fraud" and opened and filing_date and (filing_date - opened).days < 30:
            pc = False
    else:
        warnings.append("Insufficient facts to determine provisional-credit eligibility.")

    return {"errors": errors, "warnings": warnings, "card_action": action,
            "provisional_credit_eligible": pc}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)], "warnings": [], "card_action": None,
                          "provisional_credit_eligible": None}))
        sys.exit(1)
