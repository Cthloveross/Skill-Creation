#!/usr/bin/env python3
"""Conservative preflight for a proposed debit-card dispute.

Reads one JSON object from stdin and emits one JSON object to stdout.  No bank
records are read and no bank action is performed.
"""
import json
import math
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
                 "atm_cash_discrepancy", "duplicate_charge"}
LIABILITY = {"within_2_business_days": 50.0, "within_60_days": 500.0,
             "after_60_days": -1.0}


def parse_date(value, name, issues):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        issues.append(f"{name} must be MM/DD/YYYY")
        return None


def positive_number(value, name, issues):
    try:
        number = float(value)
        if not math.isfinite(number) or number < 1:
            raise ValueError
        return number
    except (TypeError, ValueError):
        issues.append(f"{name} must be a finite amount of at least $1.00")
        return None


def main(data):
    issues = []
    for name in ("transaction_id", "account_id", "card_id", "user_id"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            issues.append(f"{name} is required")
    if data.get("verified") is not True:
        issues.append("customer identity is not verified")
    if data.get("account_status") != "OPEN":
        issues.append("linked checking account is not OPEN")
    if data.get("account_restricted") is not False:
        issues.append("account restriction/hold status is not confirmed clear")
    if data.get("card_linked") is not True:
        issues.append("debit-card linkage to the checking account is not confirmed")

    category, tx_type = data.get("dispute_category"), data.get("transaction_type")
    if category not in CATEGORIES:
        issues.append("invalid dispute_category")
    if tx_type not in TYPES:
        issues.append("invalid transaction_type")
    if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal":
        issues.append("ATM cash discrepancy requires transaction_type atm_withdrawal")
    if category == "atm_deposit_not_credited" and tx_type != "atm_deposit":
        issues.append("ATM deposit-not-credited requires transaction_type atm_deposit")
    if data.get("pin_compromised") not in PINS:
        issues.append("invalid pin_compromised")
    for name in ("card_in_possession", "contacted_merchant", "police_report_filed",
                 "written_statement_provided"):
        if not isinstance(data.get(name), bool):
            issues.append(f"{name} must be boolean")

    transaction_date = parse_date(data.get("transaction_date"), "transaction_date", issues)
    discovery_date = parse_date(data.get("discovery_date"), "discovery_date", issues)
    today = parse_date(data.get("today"), "today", issues)
    if transaction_date and today:
        age = (today - transaction_date).days
        if age < 0:
            issues.append("transaction_date is in the future")
        elif age > 60:
            issues.append("transaction is older than 60 days")
    if transaction_date and discovery_date and discovery_date < transaction_date:
        issues.append("discovery_date precedes transaction_date")

    transaction_amount = positive_number(data.get("transaction_amount"), "transaction_amount", issues)
    disputed_amount = positive_number(data.get("disputed_amount"), "disputed_amount", issues)
    if transaction_amount is not None and disputed_amount is not None and disputed_amount > transaction_amount:
        issues.append("disputed_amount exceeds transaction_amount")

    tier = data.get("account_tier")
    if tier not in LIMITS:
        issues.append("account_tier must be Entry, Mid, Premium, or Elite from authorized records")
    try:
        open_disputes = int(data.get("open_disputes"))
        if isinstance(data.get("open_disputes"), bool) or open_disputes < 0:
            raise ValueError
        if tier in LIMITS and open_disputes >= LIMITS[tier]:
            issues.append("account has reached its open-dispute limit")
    except (TypeError, ValueError):
        issues.append("open_disputes must be a nonnegative integer verified from records")

    timely = data.get("timely_statement_report")
    if not isinstance(timely, bool):
        issues.append("timely_statement_report must be a verified boolean")
    band = data.get("liability_band")
    if band not in LIABILITY:
        issues.append("liability_band must be within_2_business_days, within_60_days, or after_60_days")
    liability = None
    if band in LIABILITY and disputed_amount is not None:
        liability = -1 if LIABILITY[band] == -1 else min(LIABILITY[band], disputed_amount)

    # Merchant contact is pertinent to merchant disputes.  An ATM operator is
    # not treated as a merchant for this condition.
    merchant_nonfraud = category in {"unauthorized_transaction", "duplicate_charge"}
    merchant_contact_blocks_pc = merchant_nonfraud and data.get("contacted_merchant") is not True
    eligible = bool(
        category in PC_CATEGORIES and timely is True and
        data.get("written_statement_provided") is True and
        data.get("account_status") == "OPEN" and data.get("account_restricted") is False and
        data.get("pin_compromised") != "yes_shared" and
        not (data.get("account_is_new") is True and category == "card_not_present_fraud") and
        not merchant_contact_blocks_pc
    )

    keys = ("transaction_id", "account_id", "card_id", "user_id", "dispute_category",
            "transaction_date", "discovery_date", "disputed_amount", "transaction_type",
            "card_in_possession", "pin_compromised", "contacted_merchant",
            "police_report_filed", "written_statement_provided")
    payload = {key: data.get(key) for key in keys}
    payload.update({"provisional_credit_eligible": eligible,
                    "customer_max_liability_amount": liability,
                    "card_action": ACTIONS.get(category)})
    return {"ok_to_file": not issues, "blocking_issues": issues,
            "provisional_credit_eligible": eligible,
            "customer_max_liability_amount": liability, "filing_payload": payload}


if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok_to_file": False, "blocking_issues": [str(exc)]}, sort_keys=True))
        sys.exit(1)
