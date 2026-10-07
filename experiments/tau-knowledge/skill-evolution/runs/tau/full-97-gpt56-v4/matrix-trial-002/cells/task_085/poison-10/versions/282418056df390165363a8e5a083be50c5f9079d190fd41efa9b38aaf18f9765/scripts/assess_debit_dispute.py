#!/usr/bin/env python3
"""Deterministically assess gathered debit-dispute facts.

Input: JSON object documented in SKILL.md. Output: JSON assessment. This program does
not perform bank actions and deliberately treats missing evidence as an error or warning.
"""
import json
import sys
from datetime import datetime, date

DATE_FORMAT = "%m/%d/%Y"
CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PIN_STATES = {"yes_shared", "yes_observed", "no", "unknown"}
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
LIMITS = {"entry tier": 2, "mid tier": 3, "premium tier": 4, "elite tier": 5}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        errors.append(f"{label} must be a valid MM/DD/YYYY date.")
        return None


def number(value, label, errors):
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric.")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric.")
        return None


def main(data):
    errors, warnings = [], []
    case = data.get("case") if isinstance(data.get("case"), dict) else {}
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    current = parse_date(data.get("current_date"), "current_date", errors)
    tx_date = parse_date(case.get("transaction_date"), "transaction_date", errors)
    parse_date(case.get("discovery_date"), "discovery_date", errors)

    amount = number(case.get("transaction_amount"), "transaction_amount", errors)
    disputed = number(case.get("disputed_amount"), "disputed_amount", errors)
    if amount is not None and amount < 1:
        errors.append("The transaction must be at least $1.00.")
    if disputed is not None and disputed <= 0:
        errors.append("disputed_amount must be greater than zero.")
    if amount is not None and disputed is not None and disputed > amount:
        errors.append("disputed_amount cannot exceed transaction_amount.")
    if tx_date and current:
        age = (current - tx_date).days
        if age < 0:
            errors.append("transaction_date cannot be in the future.")
        elif age > 60:
            errors.append("The transaction is more than 60 days old.")
    else:
        age = None

    category = case.get("category")
    if category not in CATEGORIES:
        errors.append("category is not a permitted dispute category.")
    if case.get("transaction_type") not in TYPES:
        errors.append("transaction_type is not permitted.")
    if case.get("pin_compromised") not in PIN_STATES:
        errors.append("pin_compromised is not permitted.")
    for field in ("card_in_possession", "contacted_merchant", "written_statement_provided", "police_report_filed"):
        if not isinstance(case.get(field), bool):
            errors.append(f"{field} must be boolean.")

    if account.get("status") != "OPEN":
        errors.append("The checking account must be OPEN.")
    if not account.get("account_id"):
        errors.append("A selected checking account ID is required.")
    if not card.get("card_id"):
        errors.append("A linked debit card ID is required.")
    if account.get("account_id") and card.get("account_id") != account.get("account_id"):
        errors.append("The debit card is not linked to the selected checking account.")

    tier = str(account.get("account_class", "")).strip().lower()
    limit = LIMITS.get(tier)
    if limit is None:
        errors.append("Account class does not have a recognized dispute limit.")
        limit = 0
    supplied_disputes = data.get("open_disputes")
    if not isinstance(supplied_disputes, list):
        errors.append("open_disputes must be a list retrieved for the verified user.")
        supplied_disputes = []
    account_id = account.get("account_id")
    open_count = sum(1 for d in supplied_disputes if isinstance(d, dict) and d.get("account_id") == account_id and d.get("status") in OPEN_STATUSES)
    if limit and open_count >= limit:
        errors.append("The account has reached its maximum number of open disputes.")

    statement_timely = case.get("statement_timely")
    if not isinstance(statement_timely, bool):
        warnings.append("Statement-based reporting timeliness is unknown; obtain it before claiming provisional credit is required.")
        statement_timely = False
    restricted = case.get("account_has_holds_or_restrictions")
    if not isinstance(restricted, bool):
        warnings.append("Account holds/restrictions were not confirmed; provisional-credit eligibility cannot be confirmed.")
        restricted = True

    opened = parse_date(account.get("date_opened"), "account.date_opened", errors)
    new_account = bool(opened and current and 0 <= (current - opened).days < 30)
    fraud = case.get("fraud_suspected")
    if not isinstance(fraud, bool):
        warnings.append("Whether fraud is suspected was not explicitly established.")
    if fraud and category == "unauthorized_transaction":
        errors.append("Suspected fraud must use a card-present or card-not-present fraud category.")
    if category == "card_present_fraud" and case.get("transaction_type") not in {"pin_purchase", "signature_purchase"}:
        errors.append("card_present_fraud requires an in-store physical transaction type.")
    if category == "card_not_present_fraud" and case.get("transaction_type") != "online_purchase":
        errors.append("card_not_present_fraud requires online_purchase transaction type.")
    if category == "atm_cash_discrepancy" and case.get("transaction_type") != "atm_withdrawal":
        errors.append("ATM cash discrepancy requires atm_withdrawal transaction type.")
    if category == "atm_deposit_not_credited" and case.get("transaction_type") != "atm_deposit":
        errors.append("ATM deposit-not-credited requires atm_deposit transaction type.")
    if fraud and amount is not None and amount > 500 and not case.get("police_report_filed"):
        warnings.append("Recommend a police report for suspected fraud over $500.")

    eligible = (
        category in PC_CATEGORIES and statement_timely and case.get("written_statement_provided") is True
        and account.get("status") == "OPEN" and not restricted
        and case.get("pin_compromised") != "yes_shared"
        and not (new_account and category == "card_not_present_fraud")
    )
    if category not in PC_CATEGORIES:
        warnings.append("This category does not require provisional credit under the stated guidelines.")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and case.get("contacted_merchant") is False:
        warnings.append("Merchant/operator contact was not attempted; provisional credit is not required for a non-fraud claim on that basis.")
        eligible = False

    return {
        "errors": errors,
        "warnings": warnings,
        "transaction_age_days": age,
        "open_dispute_count": open_count,
        "open_dispute_limit": limit,
        "card_action": ACTIONS.get(category),
        "provisional_credit_eligible": bool(eligible),
        "new_account": new_account,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)], "warnings": []}, sort_keys=True))
        sys.exit(1)
