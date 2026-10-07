#!/usr/bin/env python3
"""JSON stdin/stdout preflight validator for debit-card dispute filing.

Input is a JSON object documented in SKILL.md. Output is a JSON object with:
valid (bool), errors (list[str]), warnings (list[str]), card_action (str|null),
and provisional_credit (object). This is advisory and never performs bank actions.
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
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
TIERS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}


def is_bool(value):
    return isinstance(value, bool)


def main(data):
    errors, warnings = [], []
    required = [
        "dispute_category", "transaction_type", "transaction_date", "discovery_date",
        "disputed_amount", "card_in_possession", "pin_compromised", "contacted_merchant",
        "police_report_filed", "written_statement_provided", "account_open",
        "account_has_hold_or_restriction", "timely_within_60_days_of_statement",
        "account_age_days", "open_dispute_count", "account_tier",
    ]
    for key in required:
        if key not in data:
            errors.append("missing required preflight field: " + key)

    category = data.get("dispute_category")
    tx_type = data.get("transaction_type")
    if category not in CATEGORIES:
        errors.append("invalid dispute_category")
    if tx_type not in TYPES:
        errors.append("invalid transaction_type")
    if data.get("pin_compromised") not in PINS:
        errors.append("invalid pin_compromised")

    for key in ("transaction_date", "discovery_date"):
        value = data.get(key)
        if not isinstance(value, str):
            errors.append(key + " must be MM/DD/YYYY")
            continue
        try:
            datetime.strptime(value, "%m/%d/%Y")
        except ValueError:
            errors.append(key + " must be a real MM/DD/YYYY date")

    amount = data.get("disputed_amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 1:
        errors.append("disputed_amount must be a number of at least 1.00")

    for key in ("card_in_possession", "contacted_merchant", "police_report_filed",
                "written_statement_provided", "account_open",
                "account_has_hold_or_restriction", "timely_within_60_days_of_statement"):
        if key in data and not is_bool(data[key]):
            errors.append(key + " must be boolean")

    tier = data.get("account_tier")
    count = data.get("open_dispute_count")
    if tier not in TIERS:
        errors.append("account_tier must be Entry, Mid, Premium, or Elite")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        errors.append("open_dispute_count must be a nonnegative integer")
    elif tier in TIERS and count >= TIERS[tier]:
        errors.append("open dispute limit reached for selected account tier")

    age = data.get("account_age_days")
    if isinstance(age, bool) or not isinstance(age, int) or age < 0:
        errors.append("account_age_days must be a nonnegative integer")

    if data.get("account_open") is not True:
        errors.append("selected checking account must be OPEN")
    if data.get("account_has_hold_or_restriction") is True:
        warnings.append("account hold/restriction prevents required provisional-credit eligibility")
    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        expected = "atm_withdrawal" if category == "atm_cash_discrepancy" else "atm_deposit"
        if tx_type != expected:
            errors.append(category + " requires transaction_type " + expected)

    if category and category not in FRAUD and data.get("contacted_merchant") is False:
        warnings.append("non-fraud disputes normally require a documented merchant-resolution attempt; apply ATM-specific procedure where relevant")
    if category in FRAUD and isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 500 and not data.get("police_report_filed"):
        warnings.append("recommend a police report for suspected fraud above $500")
    if category == "atm_cash_discrepancy" and isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > 200:
        warnings.append("third-party ATM claims above $200 require an EFT Error Resolution Affidavit")

    pc_reasons = []
    pc_required = True
    if category not in PC_CATEGORIES:
        pc_required = False; pc_reasons.append("category is not in the required-credit list")
    if data.get("timely_within_60_days_of_statement") is not True:
        pc_required = False; pc_reasons.append("timely statement reporting is not established")
    if data.get("written_statement_provided") is not True:
        pc_required = False; pc_reasons.append("written statement is not provided")
    if data.get("account_open") is not True or data.get("account_has_hold_or_restriction") is True:
        pc_required = False; pc_reasons.append("account is not eligible/open without restrictions")
    if data.get("pin_compromised") == "yes_shared":
        pc_required = False; pc_reasons.append("PIN was voluntarily shared")
    if category == "card_not_present_fraud" and isinstance(age, int) and not isinstance(age, bool) and age < 30:
        pc_required = False; pc_reasons.append("new account card-not-present exception")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "card_action": ACTIONS.get(category, "keep_active") if category in CATEGORIES else None,
        "provisional_credit": {
            "required_by_general_rule": pc_required,
            "reasons_not_required_or_unconfirmed": pc_reasons,
            "note": "A confirmed Rho-Bank ATM cash discrepancy follows the immediate-credit procedure; verify the journal result separately."
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": ["invalid input: " + str(exc)], "warnings": []}, sort_keys=True))
        sys.exit(1)
