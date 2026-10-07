#!/usr/bin/env python3
"""Assess a supplied debit-card dispute case.

Input is one JSON object on stdin. Required top-level fields are now,
identity_verified, account, card, transaction, open_dispute_count, and claim.
Dates use MM/DD/YYYY. Output is JSON with readiness, findings, filing_draft,
and action recommendation. This program never calls bank tools.
"""
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
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ELIGIBLE_CATEGORIES = {"unauthorized_transaction", "card_present_fraud",
                       "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
ACTION = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}


def date_value(value, label, errors):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(f"{label} must be a valid MM/DD/YYYY date.")
        return None


def main(data):
    errors, warnings = [], []
    for field in ("now", "identity_verified", "account", "card", "transaction", "open_dispute_count", "claim"):
        if field not in data:
            errors.append(f"Missing top-level field: {field}.")
    if errors:
        return {"ready_to_file": False, "errors": errors, "warnings": warnings}

    account, card, tx, claim = data["account"], data["card"], data["transaction"], data["claim"]
    now = date_value(data["now"], "now", errors)
    tx_date = date_value(tx.get("date"), "transaction.date", errors)
    discovery = date_value(claim.get("discovery_date"), "claim.discovery_date", errors)
    opened = date_value(account.get("date_opened"), "account.date_opened", errors)

    if data.get("identity_verified") is not True:
        errors.append("Customer identity has not been verified and logged.")
    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("The linked account is not a checking account.")
    if str(account.get("status", "")).upper() != "OPEN":
        errors.append("The linked checking account is not OPEN.")
    if not card.get("linked") or not card.get("owned_by_customer"):
        errors.append("The selected debit card is not confirmed as linked to and owned by the customer.")
    if not tx.get("transaction_id"):
        errors.append("No exact transaction_id has been identified from account history.")
    try:
        amount = float(tx.get("amount"))
        if amount < 1:
            errors.append("Disputed transaction amount must be at least $1.00.")
    except (TypeError, ValueError):
        amount = None
        errors.append("transaction.amount must be numeric.")
    if now and tx_date:
        age = (now - tx_date).days
        if age < 0:
            errors.append("Transaction date cannot be in the future.")
        elif age > 60:
            errors.append("Transaction is more than 60 days old.")
    if tx.get("status") == "pending":
        warnings.append("The selected transaction is pending; confirm it is the intended transaction before filing.")

    tier = str(account.get("account_class", "")).strip().lower().replace(" tier", "")
    if tier not in LIMITS:
        errors.append("Account class is unknown; cannot determine its open-dispute limit.")
    else:
        try:
            count = int(data.get("open_dispute_count"))
            if count >= LIMITS[tier]:
                errors.append(f"Open-dispute limit reached for this account class ({LIMITS[tier]}).")
        except (TypeError, ValueError):
            errors.append("open_dispute_count must be an integer.")

    category = claim.get("category")
    if category not in CATEGORIES:
        errors.append("claim.category is not a permitted dispute category.")
    transaction_type = claim.get("transaction_type")
    if transaction_type not in TYPES:
        errors.append("claim.transaction_type is not a permitted transaction type.")
    if claim.get("pin_compromised") not in PINS:
        errors.append("claim.pin_compromised must be yes_shared, yes_observed, no, or unknown.")
    if not isinstance(claim.get("card_in_possession"), bool):
        errors.append("claim.card_in_possession must be boolean.")
    if not isinstance(claim.get("contacted_merchant"), bool):
        errors.append("claim.contacted_merchant must be boolean.")
    if not isinstance(claim.get("written_statement_provided"), bool):
        errors.append("claim.written_statement_provided must be boolean.")
    if not isinstance(claim.get("police_report_filed"), bool):
        errors.append("claim.police_report_filed must be boolean.")
    if category in {"card_present_fraud", "card_not_present_fraud"} and claim.get("fraud_suspected") is not True:
        errors.append("Fraud categories require confirmed suspected fraud.")
    if category == "unauthorized_transaction" and claim.get("fraud_suspected") is True:
        errors.append("Suspected fraud must be classified as card-present or card-not-present fraud.")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and not claim.get("contacted_merchant"):
        warnings.append("Merchant contact has not occurred for a non-fraud claim; provisional credit is not required.")
    if category in {"card_present_fraud", "card_not_present_fraud"} and amount is not None and amount > 500 and not claim.get("police_report_filed"):
        warnings.append("Recommend a police report for suspected fraud over $500.")

    action = ACTION.get(category, "keep_active")
    timely = claim.get("reported_within_60_days_of_statement")
    if not isinstance(timely, bool):
        warnings.append("Statement-date timeliness is unknown; do not determine Regulation E liability or provisional-credit eligibility yet.")
        timely = False
    new_account = bool(now and opened and (now - opened).days < 30)
    provisional = (
        timely and category in ELIGIBLE_CATEGORIES and
        claim.get("written_statement_provided") is True and
        str(account.get("status", "")).upper() == "OPEN" and
        not account.get("has_holds_or_restrictions", False) and
        claim.get("pin_compromised") != "yes_shared" and
        not (category == "card_not_present_fraud" and new_account) and
        (category in {"card_present_fraud", "card_not_present_fraud"} or claim.get("contacted_merchant") is True)
    )
    if account.get("has_holds_or_restrictions"):
        warnings.append("Account hold or restriction prevents required provisional-credit eligibility.")

    ready = not errors
    draft = None
    if ready:
        draft = {
            "transaction_id": tx["transaction_id"], "account_id": account.get("account_id"),
            "card_id": card.get("card_id"), "user_id": data.get("user_id"),
            "dispute_category": category, "transaction_date": tx["date"],
            "discovery_date": claim["discovery_date"], "disputed_amount": amount,
            "transaction_type": transaction_type, "card_in_possession": claim["card_in_possession"],
            "pin_compromised": claim["pin_compromised"], "contacted_merchant": claim["contacted_merchant"],
            "police_report_filed": claim["police_report_filed"],
            "written_statement_provided": claim["written_statement_provided"],
            "provisional_credit_eligible": provisional, "card_action": action,
        }
        for key in ("account_id", "card_id", "user_id"):
            if not draft.get(key):
                errors.append(f"Filing draft lacks {key}; obtain it from live records.")
        ready = not errors

    return {
        "ready_to_file": ready,
        "errors": errors,
        "warnings": warnings,
        "mapped_card_action": action if category in CATEGORIES else None,
        "provisional_credit_eligible": provisional,
        "provisional_credit_timeline_business_days": 20 if new_account else 10,
        "filing_draft": draft if ready else None,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ready_to_file": False, "errors": [f"Invalid input JSON: {exc.msg}"], "warnings": []}))
