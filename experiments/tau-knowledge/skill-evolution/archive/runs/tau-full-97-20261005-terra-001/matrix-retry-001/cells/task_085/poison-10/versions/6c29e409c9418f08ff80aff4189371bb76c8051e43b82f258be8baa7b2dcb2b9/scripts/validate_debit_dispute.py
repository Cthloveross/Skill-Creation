#!/usr/bin/env python3
"""Validate a gathered debit-card dispute payload without taking banking actions.

Reads a JSON object from stdin and emits JSON with blockers, warnings, the
provisional-credit determination, and filing_arguments when filing is allowed.
"""
import json
import sys

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TXN_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
OPEN_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
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
CREDIT_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
MERCHANT_CONTACT_CATEGORIES = {
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation",
}


def field(obj, key, blockers, label, expected=None):
    value = obj.get(key) if isinstance(obj, dict) else None
    if expected is bool:
        if type(value) is not bool:
            blockers.append(f"{label} must be true or false.")
    elif not isinstance(value, str) or not value.strip():
        blockers.append(f"{label} is required.")
    return value


def normalized_tier(value):
    if not isinstance(value, str):
        return None
    text = " ".join(value.lower().replace("_", " ").replace("-", " ").split())
    return text[:-5] if text.endswith(" tier") else text


def main(data):
    blockers, warnings, notices = [], [], []
    account = data.get("account", {})
    card = data.get("card", {})
    txn = data.get("transaction", {})
    case = data.get("case", {})

    verified = field(data, "verified", blockers, "Customer identity verification", bool)
    authority = field(data, "authority_verified", blockers, "Customer authority verification", bool)
    user_id = field(data, "user_id", blockers, "user_id")
    if verified is False or authority is False:
        blockers.append("Customer identity and authority must be verified before filing.")

    account_id = field(account, "account_id", blockers, "Selected account_id")
    account_type = field(account, "account_type", blockers, "Selected account type")
    account_status = field(account, "status", blockers, "Selected account status")
    tier = normalized_tier(account.get("account_class"))
    if account_type and account_type.lower() != "checking":
        blockers.append("Selected account is not a checking account.")
    if account_status and account_status.upper() != "OPEN":
        blockers.append("Selected account is not OPEN.")
    if tier not in LIMITS:
        blockers.append("Selected account class must be Entry, Mid, Premium, or Elite.")
    restricted = account.get("has_holds") is True or account.get("has_restrictions") is True

    card_id = field(card, "card_id", blockers, "card_id")
    if account_id and card.get("account_id") != account_id:
        blockers.append("Selected card is not linked to the selected checking account.")
    if user_id and card.get("user_id") != user_id:
        blockers.append("Selected card does not belong to the verified user.")
    card_status = card.get("status")
    if isinstance(card_status, str) and card_status.upper() != "ACTIVE":
        blockers.append("Selected debit card is not active.")

    transaction_id = field(txn, "transaction_id", blockers, "transaction_id")
    transaction_date = field(txn, "date", blockers, "transaction.date")
    if account_id and txn.get("account_id") != account_id:
        blockers.append("Selected transaction does not belong to the selected checking account.")
    if isinstance(txn.get("status"), str) and txn["status"].lower() != "posted":
        blockers.append("Selected transaction is not posted.")
    try:
        transaction_amount = abs(float(txn.get("amount")))
        if transaction_amount < 1:
            blockers.append("Selected transaction must be at least $1.00.")
    except (TypeError, ValueError):
        transaction_amount = None
        blockers.append("transaction.amount must be numeric.")

    category = field(case, "dispute_category", blockers, "case.dispute_category")
    transaction_type = field(case, "transaction_type", blockers, "case.transaction_type")
    discovery_date = field(case, "discovery_date", blockers, "case.discovery_date")
    if category not in CATEGORIES:
        blockers.append("case.dispute_category is unsupported.")
    if transaction_type not in TXN_TYPES:
        blockers.append("case.transaction_type is unsupported.")
    if category == "atm_cash_discrepancy" and transaction_type != "atm_withdrawal":
        blockers.append("ATM cash discrepancy requires transaction_type atm_withdrawal.")
    if category == "atm_deposit_not_credited" and transaction_type != "atm_deposit":
        blockers.append("ATM deposit-not-credited requires transaction_type atm_deposit.")
    try:
        disputed_amount = float(case.get("disputed_amount"))
        if disputed_amount <= 0:
            blockers.append("case.disputed_amount must exceed zero.")
        elif transaction_amount is not None and disputed_amount > transaction_amount:
            blockers.append("Disputed amount cannot exceed transaction amount.")
    except (TypeError, ValueError):
        disputed_amount = None
        blockers.append("case.disputed_amount must be numeric.")

    possession = field(case, "card_in_possession", blockers, "Physical-card possession", bool)
    pin = field(case, "pin_compromised", blockers, "PIN-compromise response")
    contacted = field(case, "contacted_merchant", blockers, "Merchant/ATM-contact response", bool)
    police = field(case, "police_report_filed", blockers, "Police-report status", bool)
    written = field(case, "written_statement_provided", blockers, "Written-statement status", bool)
    timely = field(case, "timely_reported_on_statement", blockers, "Statement-timeliness determination", bool)
    if pin not in PIN_VALUES:
        blockers.append("PIN-compromise response is invalid.")

    disputes = data.get("existing_disputes")
    if not isinstance(disputes, list):
        blockers.append("existing_disputes must be a list from the dispute-status lookup.")
        disputes = []
    if account_id and tier in LIMITS:
        count = sum(
            isinstance(item, dict) and item.get("account_id") == account_id
            and str(item.get("status", "")).upper() in OPEN_STATUSES
            for item in disputes
        )
        if count >= LIMITS[tier]:
            blockers.append(f"Account has {count} open disputes and has reached its {tier.title()} limit of {LIMITS[tier]}.")

    owner = case.get("atm_owner")
    journal = case.get("journal_review")
    if category == "atm_cash_discrepancy":
        if owner not in {"rho_bank", "third_party"}:
            blockers.append("ATM ownership must be rho_bank or third_party.")
        if owner == "rho_bank" and journal not in {"confirmed_discrepancy", "shows_correct_amount"}:
            blockers.append("Rho-Bank ATM journal review must be completed.")
        if owner == "rho_bank" and journal == "shows_correct_amount":
            warnings.append("Journal does not validate the shortage; formal filing remains available.")
        if owner == "third_party":
            notices.append("Third-party ATM investigation may take up to 90 days.")

    credit_reasons = []
    if timely is not True:
        credit_reasons.append("timely statement reporting was not established")
    if category not in CREDIT_CATEGORIES:
        credit_reasons.append("category is not a required provisional-credit category")
    if written is not True:
        credit_reasons.append("written statement was not provided")
    if account_status is None or str(account_status).upper() != "OPEN" or restricted:
        credit_reasons.append("account is not OPEN and unrestricted")
    if category in MERCHANT_CONTACT_CATEGORIES and contacted is False:
        credit_reasons.append("merchant was not contacted for the merchant dispute")
    if pin == "yes_shared":
        credit_reasons.append("PIN was voluntarily shared")
    eligible = not credit_reasons
    if category == "atm_cash_discrepancy" and owner == "rho_bank" and journal == "confirmed_discrepancy" and eligible:
        notices.append("Confirmed Rho-Bank ATM discrepancy: handle provisional credit immediately.")
    elif eligible:
        notices.append("Required provisional credit is due within the applicable regulatory period.")
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
            "transaction_date": transaction_date,
            "discovery_date": discovery_date,
            "disputed_amount": disputed_amount,
            "transaction_type": transaction_type,
            "card_in_possession": possession,
            "pin_compromised": pin,
            "contacted_merchant": contacted,
            "police_report_filed": police,
            "written_statement_provided": written,
            "provisional_credit_eligible": eligible,
            "card_action": CARD_ACTIONS.get(category),
        }

    return {
        "ok_to_file": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "customer_notices": notices,
        "provisional_credit": {
            "eligible": eligible,
            "immediate_for_confirmed_rho_atm": bool(
                category == "atm_cash_discrepancy" and owner == "rho_bank"
                and journal == "confirmed_discrepancy" and eligible
            ),
            "reasons_not_required": credit_reasons,
        },
        "filing_arguments": filing,
        "post_filing_card_action": CARD_ACTIONS.get(category),
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "ok_to_file": False,
            "blockers": [f"Invalid validator input: {exc}"],
            "filing_arguments": None,
        }, sort_keys=True))
        sys.exit(1)
