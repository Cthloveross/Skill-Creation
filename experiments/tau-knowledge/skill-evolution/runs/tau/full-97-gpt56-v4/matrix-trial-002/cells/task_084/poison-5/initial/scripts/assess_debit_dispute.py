#!/usr/bin/env python3
"""Validate deterministic debit-dispute prerequisites from JSON stdin.

This helper only assesses supplied facts. It never calls banking tools or files a dispute.
"""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
PROVISIONAL_CATEGORIES = FRAUD | {
    "unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"
}
NON_FRAUD = CATEGORIES - FRAUD


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{field} must be MM/DD/YYYY.")
        return None


def action_for(category):
    if category in FRAUD:
        return "close_and_reissue"
    if category == "unauthorized_transaction":
        return "freeze_pending_investigation"
    return "keep_active"


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"ready_to_file": False, "errors": [f"Invalid JSON input: {exc}"], "warnings": []}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"ready_to_file": False, "errors": ["Input must be a JSON object."], "warnings": []}))
        return

    errors, warnings = [], []
    tx_date = parse_date(data.get("transaction_date"), "transaction_date", errors)
    now = parse_date(data.get("current_date"), "current_date", errors)
    if tx_date and now:
        age = (now - tx_date).days
        if age < 0:
            errors.append("transaction_date cannot be after current_date.")
        elif age > 60:
            errors.append("Transaction is more than 60 calendar days old.")

    amount = data.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        errors.append("amount must be a numeric disputed debit amount of at least $1.00.")

    category = data.get("category")
    if category not in CATEGORIES:
        errors.append("category is not an allowed dispute category.")
    tx_type = data.get("transaction_type")
    if tx_type not in TRANSACTION_TYPES:
        errors.append("transaction_type is not allowed.")

    if data.get("account_status") != "OPEN":
        errors.append("Linked checking account must be OPEN.")
    if data.get("account_has_holds") is True:
        errors.append("Checking account has holds or restrictions.")
    elif data.get("account_has_holds") is not False:
        warnings.append("Account holds/restrictions have not been confirmed.")

    tier = data.get("tier")
    count = data.get("open_dispute_count")
    if tier not in LIMITS:
        errors.append("Checking-account tier must be Entry, Mid, Premium, or Elite.")
    elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
        errors.append("open_dispute_count must be a nonnegative integer for this account.")
    elif count >= LIMITS[tier]:
        errors.append(f"Open-dispute limit reached for {tier} tier.")

    if data.get("card_in_possession") not in (True, False):
        warnings.append("Customer must answer whether the physical card is in possession.")
    pin = data.get("pin_compromised")
    if pin not in {"yes_shared", "yes_observed", "no", "unknown"}:
        errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown.")
    fraud_suspected = data.get("fraud_suspected")
    if category in FRAUD and fraud_suspected is not True:
        warnings.append("Confirm suspected fraud before using a fraud category.")
    if category == "unauthorized_transaction" and fraud_suspected is True:
        errors.append("Suspected fraud must use a card-present or card-not-present fraud category.")
    if category in NON_FRAUD and data.get("contacted_merchant") is not True:
        errors.append("Merchant contact is required for a non-fraud dispute before filing.")
    if category and category.startswith("atm_") and data.get("atm_network_known") is not True:
        errors.append("ATM network (Rho-Bank or third-party) must be established.")

    timely = data.get("reported_within_60_days_of_statement")
    if timely not in (True, False):
        warnings.append("Statement-date reporting timeliness is unknown; provisional-credit eligibility cannot be confirmed.")
    statement = data.get("written_statement_provided")
    if statement not in (True, False):
        warnings.append("Written-statement agreement is unknown.")
    age_days = data.get("account_age_days")
    if not isinstance(age_days, int) or isinstance(age_days, bool) or age_days < 0:
        warnings.append("Account age in days is unknown or invalid.")
        age_days = None

    provisional = False
    if category in PROVISIONAL_CATEGORIES:
        provisional = (
            timely is True and statement is True and data.get("account_status") == "OPEN"
            and data.get("account_has_holds") is False and pin != "yes_shared"
            and not (category == "card_not_present_fraud" and age_days is not None and age_days < 30)
        )
    if category in PROVISIONAL_CATEGORIES and (timely not in (True, False) or statement not in (True, False) or age_days is None):
        warnings.append("Provisional-credit assessment has unresolved required facts.")

    result = {
        "ready_to_file": not errors,
        "errors": errors,
        "warnings": warnings,
        "card_action": action_for(category) if category in CATEGORIES else None,
        "provisional_credit_eligible": provisional,
        "provisional_credit_basis": "required conditions satisfied" if provisional else "not established from supplied facts",
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
