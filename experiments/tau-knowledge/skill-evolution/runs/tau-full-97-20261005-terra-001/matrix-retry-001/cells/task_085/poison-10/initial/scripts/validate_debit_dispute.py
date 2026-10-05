#!/usr/bin/env python3
"""Validate a gathered debit-card dispute case without performing bank actions.

Input: JSON object documented in SKILL.md.
Output: JSON with ok_to_file, blockers, warnings, customer_notices,
        provisional_credit, and filing_arguments (or null).
"""
import json
import re
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
CARD_ACTIONS = {
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
OPEN_DISPUTE_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
TIER_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
QUALIFYING_CREDIT_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}


def get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else default


def date_value(value, label, blockers):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", value):
        blockers.append(f"{label} must be supplied in MM/DD/YYYY format.")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        blockers.append(f"{label} is not a valid calendar date.")
        return None


def required_string(obj, key, label, blockers):
    value = get(obj, key)
    if not isinstance(value, str) or not value.strip():
        blockers.append(f"{label} is required.")
        return None
    return value


def required_bool(obj, key, label, blockers):
    value = get(obj, key, None)
    if type(value) is not bool:
        blockers.append(f"{label} must be determined as true or false.")
        return None
    return value


def normal_tier(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower().replace("_", " ").replace("-", " ")
    value = " ".join(value.split())
    if value.endswith(" tier"):
        value = value[:-5]
    return value


def main(data):
    blockers, warnings, notices = [], [], []
    account = get(data, "account", {})
    card = get(data, "card", {})
    txn = get(data, "transaction", {})
    case = get(data, "case", {})

    now = date_value(get(data, "now"), "now", blockers)
    verified = required_bool(data, "verified", "Customer identity verification", blockers)
    authority = required_bool(data, "authority_verified", "Customer authority verification", blockers)
    user_id = required_string(data, "user_id", "user_id", blockers)

    account_id = required_string(account, "account_id", "Selected account_id", blockers)
    account_type = required_string(account, "account_type", "Selected account type", blockers)
    account_status = required_string(account, "status", "Selected account status", blockers)
    account_opened = date_value(get(account, "date_opened"), "account.date_opened", blockers)
    tier = normal_tier(get(account, "account_class"))
    if tier not in TIER_LIMITS:
        blockers.append("Selected checking account class must be Entry, Mid, Premium, or Elite.")
    if account_type and account_type.strip().lower() != "checking":
        blockers.append("The selected account is not a checking account.")
    if account_status and account_status.strip().upper() != "OPEN":
        blockers.append("The debit card must be linked to an OPEN checking account.")
    if get(account, "has_holds", False) is True or get(account, "has_restrictions", False) is True:
        warnings.append("Account holds/restrictions prevent required provisional-credit eligibility.")

    card_id = required_string(card, "card_id", "card_id", blockers)
    if account_id and get(card, "account_id") != account_id:
        blockers.append("Selected debit card is not linked to the selected checking account.")
    if user_id and get(card, "user_id") != user_id:
        blockers.append("Selected debit card does not belong to the verified user.")

    transaction_id = required_string(txn, "transaction_id", "transaction_id", blockers)
    txn_date_text = required_string(txn, "date", "transaction.date", blockers)
    txn_date = date_value(txn_date_text, "transaction.date", blockers)
    if account_id and get(txn, "account_id") != account_id:
        blockers.append("Selected transaction does not belong to the selected checking account.")
    try:
        txn_amount = abs(float(get(txn, "amount")))
        if txn_amount < 1:
            blockers.append("The selected transaction must be at least $1.00.")
    except (TypeError, ValueError):
        txn_amount = None
        blockers.append("transaction.amount must be numeric.")
    if now and txn_date:
        age = (now - txn_date).days
        if age < 0:
            blockers.append("The selected transaction date cannot be in the future.")
        elif age > 60:
            blockers.append("The selected transaction is more than 60 days old.")

    category = required_string(case, "dispute_category", "case.dispute_category", blockers)
    transaction_type = required_string(case, "transaction_type", "case.transaction_type", blockers)
    if category and category not in CATEGORIES:
        blockers.append("case.dispute_category is not a supported filing category.")
    if transaction_type and transaction_type not in TRANSACTION_TYPES:
        blockers.append("case.transaction_type is not a supported transaction type.")
    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and transaction_type not in {"atm_withdrawal", "atm_deposit"}:
        blockers.append("ATM dispute categories require an ATM transaction type.")
    if category == "atm_cash_discrepancy" and transaction_type != "atm_withdrawal":
        blockers.append("ATM cash discrepancy requires transaction_type atm_withdrawal.")
    if category == "atm_deposit_not_credited" and transaction_type != "atm_deposit":
        blockers.append("ATM deposit-not-credited requires transaction_type atm_deposit.")

    discovery_text = required_string(case, "discovery_date", "case.discovery_date", blockers)
    discovery_date = date_value(discovery_text, "case.discovery_date", blockers)
    if txn_date and discovery_date and discovery_date < txn_date:
        blockers.append("Discovery date cannot precede the transaction date.")

    try:
        disputed_amount = float(get(case, "disputed_amount"))
        if disputed_amount <= 0:
            blockers.append("case.disputed_amount must be greater than zero.")
        elif txn_amount is not None and disputed_amount > txn_amount:
            blockers.append("Disputed amount cannot exceed the transaction amount.")
    except (TypeError, ValueError):
        disputed_amount = None
        blockers.append("case.disputed_amount must be numeric.")

    card_in_possession = required_bool(case, "card_in_possession", "Physical-card possession", blockers)
    pin_compromised = required_string(case, "pin_compromised", "PIN-compromise response", blockers)
    if pin_compromised and pin_compromised not in PIN_VALUES:
        blockers.append("PIN-compromise response is invalid.")
    contacted_merchant = required_bool(case, "contacted_merchant", "Merchant-contact response", blockers)
    police_report_filed = required_bool(case, "police_report_filed", "Police-report status", blockers)
    written_statement = required_bool(case, "written_statement_provided", "Written-statement consent/status", blockers)

    liability_window = required_string(case, "liability_window", "Liability timing determination", blockers)
    liability_messages = {
        "within_2_business_days": "Your maximum liability is $50 when reported within 2 business days of the statement.",
        "within_60_days": "Your maximum liability is $500 when reported within 60 days of the statement.",
        "after_60_days": "After 60 days from the statement, liability may be unlimited and recovery may not be available.",
    }
    if liability_window not in liability_messages:
        blockers.append("liability_window must be within_2_business_days, within_60_days, or after_60_days.")
    else:
        notices.append(liability_messages[liability_window])

    disputes = get(data, "existing_disputes", [])
    if not isinstance(disputes, list):
        blockers.append("existing_disputes must be a list returned from dispute-status lookup.")
        disputes = []
    if account_id and tier in TIER_LIMITS:
        open_count = sum(
            1 for item in disputes
            if isinstance(item, dict) and item.get("account_id") == account_id
            and str(item.get("status", "")).upper() in OPEN_DISPUTE_STATUSES
        )
        if open_count >= TIER_LIMITS[tier]:
            blockers.append(f"This account already has {open_count} open disputes, meeting its {tier.title()} tier limit of {TIER_LIMITS[tier]}.")

    if category == "duplicate_charge":
        earliest = required_bool(case, "is_earliest_matching_duplicate", "Earliest-duplicate confirmation", blockers)
        if earliest is False:
            blockers.append("File the earliest matching duplicate transaction first.")

    atm_owner = get(case, "atm_owner")
    journal_result = get(case, "journal_review")
    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        if atm_owner not in {"rho_bank", "third_party"}:
            blockers.append("ATM ownership must be determined as rho_bank or third_party.")
        if atm_owner == "rho_bank" and category == "atm_cash_discrepancy":
            if journal_result not in {"confirmed_discrepancy", "shows_correct_amount"}:
                blockers.append("Review the Rho-Bank ATM journal/transaction record before handling a cash discrepancy.")
            elif journal_result == "shows_correct_amount":
                warnings.append("Journal shows the recorded dispensed amount; advise that the claim is not journal-validated, though formal filing remains available.")
        if atm_owner == "third_party":
            notices.append("Third-party ATM disputes may take up to 90 days to investigate.")
        if category == "atm_cash_discrepancy" and disputed_amount is not None and disputed_amount > 200:
            notices.append("An Electronic Fund Transfer Error Resolution Affidavit must be emailed, signed, and returned within 10 business days; failure to return it may result in denial, and a false affidavit is a federal offense.")

    timely_statement = required_bool(case, "timely_reported_on_statement", "Statement-timeliness determination", blockers)
    account_restricted = get(account, "has_holds", False) is True or get(account, "has_restrictions", False) is True
    new_account = bool(now and account_opened and (now - account_opened).days < 30)
    credit_reasons = []
    if timely_statement is not True:
        credit_reasons.append("report was not established as within 60 days of the relevant statement")
    if category not in QUALIFYING_CREDIT_CATEGORIES:
        credit_reasons.append("category is not a required-provisional-credit category")
    if written_statement is not True:
        credit_reasons.append("written statement was not provided")
    if account_status is None or account_status.strip().upper() != "OPEN" or account_restricted:
        credit_reasons.append("account is not OPEN and unrestricted")
    if category not in FRAUD_CATEGORIES and category and contacted_merchant is False:
        credit_reasons.append("merchant was not contacted for a non-fraud dispute")
    if pin_compromised == "yes_shared":
        credit_reasons.append("PIN was voluntarily shared")
    if new_account and category == "card_not_present_fraud":
        credit_reasons.append("card-not-present claim is on an account open under 30 days")
    provisional_eligible = not credit_reasons

    if category in FRAUD_CATEGORIES and disputed_amount is not None and disputed_amount > 500 and police_report_filed is False:
        warnings.append("Recommend that the customer file a police report for suspected fraud over $500.")
    if category == "atm_cash_discrepancy" and atm_owner == "rho_bank" and journal_result == "confirmed_discrepancy" and provisional_eligible:
        notices.append("Confirmed Rho-Bank ATM discrepancy: issue provisional credit immediately.")
    elif provisional_eligible:
        deadline = 20 if new_account else 10
        notices.append(f"Required provisional credit should be issued within {deadline} business days.")
    else:
        warnings.append("Provisional credit is not required based on: " + "; ".join(credit_reasons) + ".")

    filing = None
    if not blockers:
        filing = {
            "transaction_id": transaction_id,
            "account_id": account_id,
            "card_id": card_id,
            "user_id": user_id,
            "dispute_category": category,
            "transaction_date": txn_date_text,
            "discovery_date": discovery_text,
            "disputed_amount": disputed_amount,
            "transaction_type": transaction_type,
            "card_in_possession": card_in_possession,
            "pin_compromised": pin_compromised,
            "contacted_merchant": contacted_merchant,
            "police_report_filed": police_report_filed,
            "written_statement_provided": written_statement,
            "provisional_credit_eligible": provisional_eligible,
            "card_action": CARD_ACTIONS.get(category),
        }

    return {
        "ok_to_file": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "customer_notices": notices,
        "provisional_credit": {
            "eligible": provisional_eligible,
            "reasons_not_required": credit_reasons,
            "immediate_for_confirmed_rho_atm": bool(
                category == "atm_cash_discrepancy" and atm_owner == "rho_bank"
                and journal_result == "confirmed_discrepancy" and provisional_eligible
            ),
        },
        "filing_arguments": filing,
        "post_filing_card_action": CARD_ACTIONS.get(category),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok_to_file": False, "blockers": [f"Invalid validator input: {exc}"], "filing_arguments": None}))
        sys.exit(1)
