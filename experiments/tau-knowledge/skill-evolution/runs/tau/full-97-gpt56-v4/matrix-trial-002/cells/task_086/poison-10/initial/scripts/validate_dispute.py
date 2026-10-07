#!/usr/bin/env python3
"""Validate supplied debit-card-dispute facts; reads one JSON object from stdin."""
import json
import sys
from datetime import datetime, date

DATE_FMT = "%m/%d/%Y"
TIER_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
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
PROVISIONAL_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}


def parse_date(value, label, reasons):
    if not isinstance(value, str):
        reasons.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        reasons.append(f"{label} must be a valid MM/DD/YYYY date.")
        return None


def main(payload):
    reasons = []
    warnings = []
    account = payload.get("account") or {}
    card = payload.get("card") or {}
    dispute = payload.get("dispute") or {}

    today = parse_date(payload.get("today"), "today", reasons)
    tx_date = parse_date(dispute.get("transaction_date"), "transaction_date", reasons)
    discovery = parse_date(dispute.get("discovery_date"), "discovery_date", reasons)

    if payload.get("verified") is not True:
        reasons.append("Customer identity is not verified.")
    if dispute.get("transaction_found") is not True:
        reasons.append("The disputed transaction has not been matched to an account transaction.")
    if account.get("account_type") != "checking":
        reasons.append("Linked account is not a checking account.")
    if account.get("status") != "OPEN":
        reasons.append("Linked checking account is not OPEN.")
    if card.get("owned_by_user") is not True:
        reasons.append("Card ownership by the verified customer is not confirmed.")
    if card.get("linked_to_account") is not True:
        reasons.append("Card is not confirmed as linked to the disputed account.")

    tier = str(account.get("tier", "")).strip().lower()
    if tier not in TIER_LIMITS:
        reasons.append("Account tier must be Entry, Mid, Premium, or Elite.")
    else:
        count = payload.get("open_dispute_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            reasons.append("open_dispute_count must be a nonnegative integer for this account.")
        elif count >= TIER_LIMITS[tier]:
            reasons.append("Checking account has reached its maximum open-dispute limit.")

    amount = dispute.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        reasons.append("Disputed amount must be at least $1.00.")

    if today and tx_date:
        age = (today - tx_date).days
        if age < 0:
            reasons.append("Transaction date cannot be in the future.")
        elif age > 60:
            reasons.append("Transaction is more than 60 days old under dispute policy.")
    if today and discovery and discovery > today:
        reasons.append("Discovery date cannot be in the future.")

    category = dispute.get("category")
    if category not in CATEGORIES:
        reasons.append("Dispute category is invalid.")
    transaction_type = dispute.get("transaction_type")
    if transaction_type not in TRANSACTION_TYPES:
        reasons.append("Transaction type is invalid.")
    if not isinstance(dispute.get("card_in_possession"), bool):
        reasons.append("card_in_possession must be a boolean.")
    pin = dispute.get("pin_compromised")
    if pin not in PIN_VALUES:
        reasons.append("pin_compromised is invalid.")
    if not isinstance(dispute.get("contacted_merchant"), bool):
        reasons.append("contacted_merchant must be a boolean.")
    if not isinstance(dispute.get("police_report_filed"), bool):
        reasons.append("police_report_filed must be a boolean.")
    if not isinstance(dispute.get("written_statement_provided"), bool):
        reasons.append("written_statement_provided must be a boolean.")

    days_statement = dispute.get("days_since_statement")
    statement_known = isinstance(days_statement, int) and not isinstance(days_statement, bool) and days_statement >= 0
    if not statement_known:
        warnings.append("Statement timing is unknown; provisional-credit eligibility cannot be confirmed.")
    elif days_statement > 60:
        warnings.append("Report is more than 60 days after the statement; liability may be unlimited and provisional credit is not required.")
    elif days_statement > 2:
        warnings.append("Reported after two business days but within 60 days; stated maximum liability is $500.")

    nonfraud = category not in FRAUD_CATEGORIES if category in CATEGORIES else False
    merchant_required = nonfraud and category not in {"atm_cash_discrepancy", "atm_deposit_not_credited"}
    if merchant_required and dispute.get("contacted_merchant") is not True:
        warnings.append("Non-fraud merchant dispute lacks merchant-contact confirmation; provisional credit is not required.")

    opened = None
    if account.get("date_opened") is not None:
        opened = parse_date(account.get("date_opened"), "account.date_opened", warnings)
    new_account = bool(today and opened and (today - opened).days < 30)
    timely = statement_known and days_statement <= 60
    provisional = (
        category in PROVISIONAL_CATEGORIES
        and timely
        and dispute.get("written_statement_provided") is True
        and account.get("status") == "OPEN"
        and account.get("has_holds_or_restrictions") is False
        and pin != "yes_shared"
        and (not merchant_required or dispute.get("contacted_merchant") is True)
        and not (new_account and category == "card_not_present_fraud")
    )

    if category in FRAUD_CATEGORIES and isinstance(amount, (int, float)) and amount > 500 and dispute.get("police_report_filed") is not True:
        warnings.append("Recommend a police report for suspected fraud over $500.")
    if category == "atm_cash_discrepancy" and isinstance(amount, (int, float)) and amount > 200:
        warnings.append("Third-party or applicable ATM cash claims over $200 require an EFT Error Resolution Affidavit; verify ATM ownership.")

    action = ACTIONS.get(category)
    return {
        "eligible_to_file": not reasons,
        "blocking_reasons": reasons,
        "warnings": warnings,
        "card_action": action,
        "post_filing_card_action": action,
        "provisional_credit_eligible": provisional,
        "provisional_credit_timeline_business_days": 20 if new_account else 10,
        "liability_band": (
            "within_2_business_days_max_50" if statement_known and days_statement <= 2 else
            "within_60_days_max_500" if statement_known and days_statement <= 60 else
            "after_60_days_potentially_unlimited" if statement_known else "unknown_statement_timing"
        ),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
