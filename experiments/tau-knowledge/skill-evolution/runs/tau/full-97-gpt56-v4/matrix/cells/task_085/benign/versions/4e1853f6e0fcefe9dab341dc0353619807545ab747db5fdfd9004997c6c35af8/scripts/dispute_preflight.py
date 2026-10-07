#!/usr/bin/env python3
"""Validate a debit-card dispute proposal. Reads one JSON object from stdin."""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
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
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}


def date_value(value, key, issues):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        issues.append(f"{key} must be MM/DD/YYYY")
        return None


def main(data):
    issues = []
    required_ids = ("transaction_id", "account_id", "card_id", "user_id")
    for key in required_ids:
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(f"missing {key}")
    if data.get("verified") is not True:
        issues.append("customer identity is not verified")
    if data.get("account_status") != "OPEN":
        issues.append("linked checking account is not OPEN")
    if data.get("account_restricted") is not False:
        issues.append("account restriction/hold status is not confirmed clear")
    if data.get("card_linked") is not True:
        issues.append("debit card linkage to the checking account is not confirmed")

    category = data.get("dispute_category")
    tx_type = data.get("transaction_type")
    if category not in CATEGORIES:
        issues.append("invalid dispute_category")
    if tx_type not in TYPES:
        issues.append("invalid transaction_type")
    if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal":
        issues.append("ATM cash discrepancy requires transaction_type atm_withdrawal")
    if data.get("pin_compromised") not in PINS:
        issues.append("invalid pin_compromised")
    if not isinstance(data.get("card_in_possession"), bool):
        issues.append("card_in_possession must be boolean")
    for key in ("contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not isinstance(data.get(key), bool):
            issues.append(f"{key} must be boolean")

    transaction_date = date_value(data.get("transaction_date"), "transaction_date", issues)
    discovery_date = date_value(data.get("discovery_date"), "discovery_date", issues)
    today = date_value(data.get("today"), "today", issues)
    if transaction_date and today:
        age = (today - transaction_date).days
        if age < 0:
            issues.append("transaction_date is in the future")
        elif age > 60:
            issues.append("transaction is older than 60 days")
    if transaction_date and discovery_date and discovery_date < transaction_date:
        issues.append("discovery_date precedes transaction_date")

    try:
        transaction_amount = float(data.get("transaction_amount"))
        disputed_amount = float(data.get("disputed_amount"))
        if transaction_amount < 1:
            issues.append("transaction amount must be at least $1.00")
        if disputed_amount < 1:
            issues.append("disputed amount must be at least $1.00")
        if disputed_amount > transaction_amount:
            issues.append("disputed amount exceeds transaction amount")
    except (TypeError, ValueError):
        issues.append("transaction_amount and disputed_amount must be numeric")

    tier = data.get("account_tier")
    if tier not in LIMITS:
        issues.append("account tier must be Entry, Mid, Premium, or Elite")
    try:
        open_disputes = int(data.get("open_disputes"))
        if open_disputes < 0:
            raise ValueError
        if tier in LIMITS and open_disputes >= LIMITS[tier]:
            issues.append("account has reached its open-dispute limit")
    except (TypeError, ValueError):
        issues.append("open_disputes must be a nonnegative integer verified from records")

    timely = data.get("timely_statement_report")
    if not isinstance(timely, bool):
        issues.append("timely_statement_report must be a verified boolean")
    eligible = bool(
        category in PC_CATEGORIES and timely is True and
        data.get("written_statement_provided") is True and
        data.get("account_status") == "OPEN" and
        data.get("account_restricted") is False and
        data.get("pin_compromised") != "yes_shared" and
        not (data.get("account_is_new") is True and category == "card_not_present_fraud")
    )

    payload_keys = ["transaction_id", "account_id", "card_id", "user_id", "dispute_category",
                    "transaction_date", "discovery_date", "disputed_amount", "transaction_type",
                    "card_in_possession", "pin_compromised", "contacted_merchant",
                    "police_report_filed", "written_statement_provided"]
    payload = {k: data.get(k) for k in payload_keys}
    payload["provisional_credit_eligible"] = eligible
    payload["card_action"] = ACTIONS.get(category)
    return {"ok_to_file": not issues, "blocking_issues": issues,
            "provisional_credit_eligible": eligible, "filing_payload": payload}


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(source), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok_to_file": False, "blocking_issues": [str(exc)]}))
        sys.exit(1)
