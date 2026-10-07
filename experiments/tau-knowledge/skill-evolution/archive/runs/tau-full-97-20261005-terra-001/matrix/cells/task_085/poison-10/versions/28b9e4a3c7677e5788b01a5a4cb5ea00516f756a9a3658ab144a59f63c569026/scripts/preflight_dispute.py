#!/usr/bin/env python3
"""Pure JSON preflight validation for a debit-card dispute filing."""
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
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ONGOING = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
                 "atm_cash_discrepancy", "duplicate_charge"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}


def date(value, label, errors):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(label + " must be MM/DD/YYYY")
        return None


def tier_for(account):
    explicit = str(account.get("tier", "")).strip().lower()
    if explicit in LIMITS:
        return explicit
    value = str(account.get("account_class", "")).strip().lower()
    if any(x in value for x in ("entry", "light blue", "light green", "green fee-free")):
        return "entry"
    if "premium" in value or "evergreen" in value:
        return "premium"
    if "elite" in value or "bluest" in value:
        return "elite"
    if "mid" in value or value in {"blue account", "green account", "green account (checking)"}:
        return "mid"
    return None


def main(raw):
    errors, warnings = [], []
    account = raw.get("account") or {}
    card = raw.get("card") or {}
    tx = raw.get("transaction") or {}
    claim = raw.get("claim") or {}
    today = date(raw.get("today"), "today", errors)
    tx_date = date(tx.get("date"), "transaction.date", errors)
    date(claim.get("discovery_date"), "claim.discovery_date", errors)

    if raw.get("identity_verified") is not True:
        errors.append("customer identity and authority are not verified")
    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("selected account is not a checking account")
    if str(account.get("status", "")).upper() != "OPEN":
        errors.append("checking account is not OPEN")
    if not account.get("account_id") or card.get("account_id") != account.get("account_id"):
        errors.append("card is not confirmed linked to selected checking account")
    if not card.get("card_id") or not card.get("user_id"):
        errors.append("linked card ID and cardholder user ID are required")
    if tx.get("account_id") != account.get("account_id") or not tx.get("transaction_id"):
        errors.append("transaction is not confirmed on selected account")

    tier = tier_for(account)
    if not tier:
        errors.append("account tier cannot be determined")
    active = sum(1 for d in (raw.get("open_disputes") or [])
                 if d.get("account_id") == account.get("account_id") and str(d.get("status", "")).upper() in ONGOING)
    if tier and active >= LIMITS[tier]:
        errors.append("open-dispute limit reached for this account tier")

    try:
        amount = float(claim.get("disputed_amount"))
    except (TypeError, ValueError):
        amount = 0.0
        errors.append("claim.disputed_amount must be numeric")
    if amount < 1.0:
        errors.append("disputed amount must be at least $1.00")
    try:
        tx_amount = abs(float(tx.get("amount")))
        if amount > tx_amount:
            errors.append("disputed amount cannot exceed matched transaction amount")
    except (TypeError, ValueError):
        errors.append("transaction.amount must be numeric")
    if today and tx_date:
        age = (today - tx_date).days
        if age < 0 or age > 60:
            errors.append("transaction is not within the permitted 60-day filing window")

    category = claim.get("category")
    transaction_type = claim.get("transaction_type")
    if category not in CATEGORIES:
        errors.append("claim.category is not an allowed dispute category")
    if transaction_type not in TYPES:
        errors.append("claim.transaction_type is not an allowed transaction type")
    if category == "atm_cash_discrepancy" and transaction_type != "atm_withdrawal":
        errors.append("ATM cash discrepancy requires transaction_type atm_withdrawal")
    if category == "atm_deposit_not_credited" and transaction_type != "atm_deposit":
        errors.append("ATM deposit claim requires transaction_type atm_deposit")
    if claim.get("card_in_possession") not in (True, False):
        errors.append("card_in_possession must be boolean")
    if claim.get("pin_compromised") not in PINS:
        errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown")
    for key in ("contacted_merchant", "police_report_filed", "written_statement_provided"):
        if claim.get(key) not in (True, False):
            errors.append(key + " must be boolean")

    action = ACTIONS.get(category, "keep_active")
    unrestricted = account.get("unrestricted") is True
    timely = claim.get("timely_statement_reported") is True
    opened = date(account.get("date_opened"), "account.date_opened", warnings)
    new_account = bool(today and opened and (today - opened).days < 30)
    pc = (timely and category in PC_CATEGORIES and claim.get("written_statement_provided") is True
          and unrestricted and not (category not in FRAUD and claim.get("contacted_merchant") is False)
          and claim.get("pin_compromised") != "yes_shared"
          and not (new_account and category == "card_not_present_fraud"))
    if not timely:
        warnings.append("provisional credit is not marked required without confirmed statement-timely reporting")
    if not unrestricted:
        warnings.append("provisional credit is not marked required without confirmed open unrestricted account standing")
    if category in FRAUD and amount > 500 and claim.get("police_report_filed") is not True:
        warnings.append("recommend a police report for suspected fraud over $500")
    if category == "atm_cash_discrepancy":
        owner = claim.get("atm_owner")
        if owner not in ("rho_bank", "third_party"):
            warnings.append("determine whether the ATM is Rho-Bank owned or third-party")
        if owner == "rho_bank" and claim.get("journal_discrepancy_confirmed") is True:
            warnings.append("confirmed Rho-Bank ATM discrepancy requires immediate provisional-credit handling")
        if amount > 200:
            warnings.append("ATM cash discrepancy over $200 requires Electronic Fund Transfer Error Resolution Affidavit notice")

    payload = None
    if not errors:
        payload = {
            "transaction_id": tx.get("transaction_id"), "account_id": account.get("account_id"),
            "card_id": card.get("card_id"), "user_id": card.get("user_id"),
            "dispute_category": category, "transaction_date": tx.get("date"),
            "discovery_date": claim.get("discovery_date"), "disputed_amount": amount,
            "transaction_type": transaction_type, "card_in_possession": claim.get("card_in_possession"),
            "pin_compromised": claim.get("pin_compromised"), "contacted_merchant": claim.get("contacted_merchant"),
            "police_report_filed": claim.get("police_report_filed"),
            "written_statement_provided": claim.get("written_statement_provided"),
            "provisional_credit_eligible": pc, "card_action": action,
        }
    return {"valid_to_file": not errors, "blockers": errors, "warnings": warnings,
            "account_tier": tier, "ongoing_disputes_for_account": active,
            "card_action": action, "provisional_credit_eligible": pc, "filing_args": payload}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"valid_to_file": False, "blockers": ["invalid input: " + str(exc)], "filing_args": None}))
