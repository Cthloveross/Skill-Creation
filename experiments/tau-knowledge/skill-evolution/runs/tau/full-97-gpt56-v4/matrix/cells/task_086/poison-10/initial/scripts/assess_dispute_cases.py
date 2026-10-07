#!/usr/bin/env python3
"""Validate deterministic debit-dispute intake fields. Reads JSON stdin, writes JSON stdout."""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ELIGIBLE_PC = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
               "atm_cash_discrepancy", "duplicate_charge"}


def date(value):
    return datetime.strptime(value, "%m/%d/%Y").date()


def action(category):
    if category in {"card_present_fraud", "card_not_present_fraud"}:
        return "close_and_reissue"
    if category == "unauthorized_transaction":
        return "freeze_pending_investigation"
    return "keep_active"


def assess(case, as_of):
    errors, warnings = [], []
    category = case.get("category")
    amount = case.get("disputed_amount")
    try:
        age = (as_of - date(case["transaction_date"])).days
        if age < 0:
            errors.append("transaction_date cannot be in the future")
        elif age > 60:
            errors.append("transaction is older than 60 days")
        date(case["discovery_date"])
    except (KeyError, TypeError, ValueError):
        errors.append("transaction_date and discovery_date must use MM/DD/YYYY")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        errors.append("disputed_amount must be at least 1.00")
    if category not in CATEGORIES:
        errors.append("category is not a permitted dispute category")
    if case.get("transaction_type") not in TYPES:
        errors.append("transaction_type is not permitted")
    if case.get("account_open") is not True:
        errors.append("linked checking account must be confirmed OPEN")
    tier = str(case.get("tier", "")).lower()
    if tier not in LIMITS:
        errors.append("tier must be Entry, Mid, Premium, or Elite")
    elif not isinstance(case.get("open_disputes"), int):
        errors.append("open_disputes must be an integer from live dispute history")
    elif case["open_disputes"] >= LIMITS[tier]:
        errors.append("account has reached its maximum open-dispute limit")
    if case.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown"}:
        errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown")
    fraud = case.get("fraud_suspected")
    if fraud is True and category == "unauthorized_transaction":
        errors.append("suspected fraud requires a card_present_fraud or card_not_present_fraud category")
    if fraud is True and category in {"card_present_fraud", "card_not_present_fraud"}:
        physical = case.get("physical_present")
        if category == "card_present_fraud" and physical is not True:
            errors.append("card_present_fraud requires confirmed physical-present use")
        if category == "card_not_present_fraud" and physical is not False:
            errors.append("card_not_present_fraud requires confirmed online/phone use")
    nonfraud_merchant = category in {"goods_services_not_received", "incorrect_amount", "recurring_charge_after_cancellation"}
    if nonfraud_merchant and case.get("merchant_contacted") is not True:
        warnings.append("merchant contact is required/expected before this non-fraud merchant dispute")
    pc = category in ELIGIBLE_PC and case.get("written_statement_provided") is True
    if case.get("pin_compromised") == "yes_shared":
        pc = False
    if category == "card_not_present_fraud" and isinstance(case.get("account_age_days"), int) and case["account_age_days"] < 30:
        pc = False
    warnings.append("Statement-date reporting timeliness and account holds/restrictions require live confirmation.")
    return {"errors": errors, "warnings": warnings, "suggested_category": category,
            "card_action": action(category) if category in CATEGORIES else None,
            "provisional_credit_required_if_timely_reported": pc}


def main():
    payload = json.load(sys.stdin)
    try:
        as_of = date(payload["as_of"])
    except (KeyError, TypeError, ValueError):
        raise SystemExit("as_of is required in MM/DD/YYYY format")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise SystemExit("cases must be a JSON list")
    print(json.dumps({"results": [assess(c, as_of) for c in cases]}, indent=2))

if __name__ == "__main__":
    main()
