#!/usr/bin/env python3
"""Validate a normalized debit-card dispute plan; reads JSON stdin and writes JSON stdout."""
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
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
                 "atm_cash_discrepancy", "duplicate_charge"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}

def parse_date(value):
    return datetime.strptime(value, "%m/%d/%Y").date()

def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    blockers, warnings = [], []
    required = ["current_date", "transaction_date", "amount", "account_type", "account_status",
                "account_class", "card_linked", "verification_logged", "open_dispute_count",
                "category", "transaction_type", "written_statement_provided",
                "timely_statement_report", "account_restricted", "contacted_merchant",
                "pin_compromised", "account_age_days"]
    missing = [k for k in required if k not in data]
    if missing:
        print(json.dumps({"eligible_to_file": False, "blockers": ["missing fields: " + ", ".join(missing)]}, sort_keys=True))
        return
    try:
        age = (parse_date(data["current_date"]) - parse_date(data["transaction_date"])).days
    except Exception:
        blockers.append("dates must use MM/DD/YYYY and form a valid interval")
        age = None
    category = data["category"]
    account_class = str(data["account_class"]).strip().lower().replace(" tier", "")
    if not data["verification_logged"]:
        blockers.append("customer verification has not been logged")
    if str(data["account_type"]).lower() != "checking":
        blockers.append("debit card dispute requires a checking account")
    if str(data["account_status"]).upper() != "OPEN":
        blockers.append("checking account is not OPEN")
    if not data["card_linked"]:
        blockers.append("debit card is not linked to the selected checking account")
    try:
        if float(data["amount"]) < 1:
            blockers.append("transaction amount is below $1.00")
    except (TypeError, ValueError):
        blockers.append("amount must be numeric")
    if age is not None and (age < 0 or age > 60):
        blockers.append("transaction is not within 60 days")
    if category not in CATEGORIES:
        blockers.append("invalid dispute category")
    if data["transaction_type"] not in TYPES:
        blockers.append("invalid transaction type")
    if account_class not in LIMITS:
        blockers.append("unrecognized checking account class")
    else:
        try:
            if int(data["open_dispute_count"]) >= LIMITS[account_class]:
                blockers.append("account has reached its open-dispute limit")
        except (TypeError, ValueError):
            blockers.append("open_dispute_count must be an integer")
    if category == "duplicate_charge" and data.get("duplicate_rank") not in (None, 1):
        blockers.append("select the earliest duplicate transaction first")
    if category in {"card_present_fraud", "card_not_present_fraud"} and data.get("fraud_suspected") is False:
        blockers.append("fraud category conflicts with fraud_suspected=false")
    if category == "unauthorized_transaction" and data.get("fraud_suspected") is True:
        blockers.append("suspected fraud must use a card-present or card-not-present fraud category")
    merchant_categories = {"duplicate_charge", "incorrect_amount", "goods_services_not_received", "recurring_charge_after_cancellation"}
    if category in merchant_categories and not data["contacted_merchant"]:
        warnings.append("merchant has not been contacted; filing may proceed but provisional credit is not required")
    action = ACTIONS.get(category, "keep_active")
    pc_required = (
        category in PC_CATEGORIES and bool(data["timely_statement_report"])
        and bool(data["written_statement_provided"])
        and str(data["account_status"]).upper() == "OPEN"
        and not bool(data["account_restricted"])
        and data["pin_compromised"] != "yes_shared"
        and not (category == "card_not_present_fraud" and int(data["account_age_days"]) < 30)
        and not (category in merchant_categories and not data["contacted_merchant"])
    )
    print(json.dumps({
        "eligible_to_file": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "transaction_age_days": age,
        "card_action": action,
        "provisional_credit_required": pc_required,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
