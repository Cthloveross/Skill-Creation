#!/usr/bin/env python3
"""Validate and plan a debit-card ATM cash-discrepancy dispute.

Input JSON schema (all values come from current runtime lookups):
{
  "today": "MM/DD/YYYY",
  "reg_e_disclosure_given": true,
  "verified_identity_fields": ["date_of_birth", "address"],
  "identity_log_completed": true,
  "user_id": "...",
  "account": {
    "account_id": "...", "account_type": "checking", "account_class": "Entry",
    "status": "OPEN", "belongs_to_user": true, "balance_verified": true,
    "standing_confirmed": true, "has_holds": false, "has_restrictions": false,
    "date_opened": "MM/DD/YYYY"
  },
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "transaction": {
    "transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY",
    "amount": -300.0, "type": "atm_withdrawal", "matched_to_customer": true
  },
  "disputes": [{"account_id": "...", "status": "OPEN"}],
  "atm": {"owner": "rho_bank", "journal_outcome": "confirmed_discrepancy"},
  "statement_date": "MM/DD/YYYY",
  "dispute": {
    "dispute_category": "atm_cash_discrepancy", "transaction_type": "atm_withdrawal",
    "transaction_date": "MM/DD/YYYY", "discovery_date": "MM/DD/YYYY",
    "disputed_amount": 100.0, "card_in_possession": true, "pin_compromised": "no",
    "contacted_merchant": false, "police_report_filed": false,
    "written_statement_provided": true
  },
  "same_card_categories": ["atm_cash_discrepancy"],
  "international_or_foreign_pos": false
}

The script does not access tools, make decisions about a customer beyond supplied facts,
or file a dispute. `standing_confirmed` may only be true when runtime account information
establishes OPEN standing with no holds or restrictions.
"""
import json
import sys
from datetime import datetime, date, timedelta

INPUT_SCHEMA = "See module docstring. All dates use MM/DD/YYYY."

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
TIER_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
UNRESOLVED = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
ACTION_BY_CATEGORY = {
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
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
PROVISIONAL_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be a MM/DD/YYYY string.")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{label} must be a valid MM/DD/YYYY date.")
        return None


def number(value, label, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be numeric.")
        return None
    return float(value)


def require_bool(container, key, errors, prefix=""):
    value = container.get(key)
    if not isinstance(value, bool):
        errors.append(f"{prefix}{key} must be boolean.")
        return False
    return value


def normalized_tier(value):
    text = str(value or "").strip().lower().replace(" tier", "")
    return text


def main(case):
    errors, warnings = [], []
    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    card = case.get("card") if isinstance(case.get("card"), dict) else {}
    tx = case.get("transaction") if isinstance(case.get("transaction"), dict) else {}
    dispute = case.get("dispute") if isinstance(case.get("dispute"), dict) else {}
    atm = case.get("atm") if isinstance(case.get("atm"), dict) else {}

    today = parse_date(case.get("today"), "today", errors)
    if not require_bool(case, "reg_e_disclosure_given", errors):
        errors.append("Give the Regulation E liability disclosure before proceeding.")
    verified = case.get("verified_identity_fields")
    allowed_identity = {"date_of_birth", "address", "email", "phone_number"}
    if not isinstance(verified, list) or len(set(verified) & allowed_identity) < 2:
        errors.append("At least two verified identity fields are required.")
    if not require_bool(case, "identity_log_completed", errors):
        errors.append("Successful identity verification must be logged before filing.")
    user_id = case.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("A verified user_id is required.")

    account_id = account.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        errors.append("Selected account_id is required.")
    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("The selected account must be a checking account.")
    if str(account.get("status", "")).upper() != "OPEN":
        errors.append("The selected checking account must be OPEN.")
    for key, message in [
        ("belongs_to_user", "Account ownership must be confirmed."),
        ("balance_verified", "Account balance must be reviewed before the banking action."),
        ("standing_confirmed", "Account standing (including no holds/restrictions) must be confirmed."),
    ]:
        if not require_bool(account, key, errors, "account."):
            errors.append(message)
    if account.get("has_holds") is not False or account.get("has_restrictions") is not False:
        errors.append("An account with a hold or restriction is not eligible for required provisional-credit determination.")

    tier = normalized_tier(account.get("account_class"))
    if tier not in TIER_LIMITS:
        errors.append("Account class must map to Entry, Mid, Premium, or Elite tier.")
    disputes = case.get("disputes")
    if not isinstance(disputes, list):
        errors.append("disputes must be the user's dispute-status list.")
        disputes = []
    unresolved_count = sum(
        1 for item in disputes if isinstance(item, dict)
        and item.get("account_id") == account_id
        and str(item.get("status", "")).upper() in UNRESOLVED
    )
    if tier in TIER_LIMITS and unresolved_count >= TIER_LIMITS[tier]:
        errors.append(f"Selected account already has {unresolved_count} unresolved disputes; {tier.title()} limit is {TIER_LIMITS[tier]}.")

    if not isinstance(card.get("card_id"), str) or not card.get("card_id"):
        errors.append("A linked debit card_id is required.")
    if card.get("account_id") != account_id:
        errors.append("The debit card must be linked to the selected checking account.")
    if card.get("user_id") != user_id:
        errors.append("The debit card must belong to the verified user.")
    if str(card.get("status", "")).upper() == "CLOSED":
        errors.append("A closed historical debit card cannot be used for this filing.")

    if not isinstance(tx.get("transaction_id"), str) or not tx.get("transaction_id"):
        errors.append("A transaction_id from account history is required.")
    if tx.get("account_id") != account_id:
        errors.append("Transaction must belong to the selected account.")
    if not require_bool(tx, "matched_to_customer", errors, "transaction."):
        errors.append("Transaction date, ATM, and withdrawal amount must be matched to the customer claim.")
    tx_date = parse_date(tx.get("date"), "transaction.date", errors)
    tx_amount = number(tx.get("amount"), "transaction.amount", errors)
    if str(tx.get("type", "")) != "atm_withdrawal":
        errors.append("The selected transaction must be an atm_withdrawal record.")
    if tx_amount is not None and abs(tx_amount) < 1:
        errors.append("Transaction must be at least $1.00.")
    if today and tx_date:
        age = (today - tx_date).days
        if age < 0 or age > 60:
            errors.append("Transaction must be no more than 60 calendar days old.")

    category = dispute.get("dispute_category")
    transaction_type = dispute.get("transaction_type")
    if category not in CATEGORIES:
        errors.append("dispute.dispute_category is invalid.")
    if transaction_type not in TRANSACTION_TYPES:
        errors.append("dispute.transaction_type is invalid.")
    if category != "atm_cash_discrepancy":
        errors.append("This Skill requires dispute_category atm_cash_discrepancy.")
    if transaction_type != "atm_withdrawal":
        errors.append("An ATM cash discrepancy requires transaction_type atm_withdrawal.")
    filing_tx_date = parse_date(dispute.get("transaction_date"), "dispute.transaction_date", errors)
    discovery_date = parse_date(dispute.get("discovery_date"), "dispute.discovery_date", errors)
    if tx_date and filing_tx_date and tx_date != filing_tx_date:
        errors.append("Dispute transaction_date must match the selected transaction date.")
    if tx_date and discovery_date and discovery_date < tx_date:
        errors.append("discovery_date cannot be before the transaction date.")
    amount = number(dispute.get("disputed_amount"), "dispute.disputed_amount", errors)
    if amount is not None:
        if amount < 1:
            errors.append("ATM cash shortage disputed_amount must be at least $1.00.")
        if tx_amount is not None and amount > abs(tx_amount):
            errors.append("Disputed shortage cannot exceed the withdrawal amount.")
    require_bool(dispute, "card_in_possession", errors, "dispute.")
    if dispute.get("pin_compromised") not in PIN_VALUES:
        errors.append("dispute.pin_compromised is invalid.")
    require_bool(dispute, "contacted_merchant", errors, "dispute.")
    require_bool(dispute, "police_report_filed", errors, "dispute.")
    written = require_bool(dispute, "written_statement_provided", errors, "dispute.")

    owner = atm.get("owner")
    if owner not in {"rho_bank", "third_party"}:
        errors.append("ATM owner must be determined as rho_bank or third_party.")
    journal_outcome = atm.get("journal_outcome")
    if owner == "rho_bank" and journal_outcome not in {"confirmed_discrepancy", "shows_requested_amount", "unavailable"}:
        errors.append("Rho-Bank ATM journal review outcome is required.")
    if owner == "rho_bank" and journal_outcome == "shows_requested_amount":
        warnings.append("Journal shows requested amount dispensed; explain it does not validate the claim, while allowing formal filing.")

    statement_date = parse_date(case.get("statement_date"), "statement_date", errors)
    timely = False
    if statement_date and discovery_date:
        timely = discovery_date <= statement_date + timedelta(days=60)
        if not timely:
            warnings.append("Reporting is more than 60 days after the supplied statement date; required provisional credit is not established.")

    opened = parse_date(account.get("date_opened"), "account.date_opened", errors)
    new_account = bool(today and opened and 0 <= (today - opened).days < 30)
    eligible = bool(
        category in PROVISIONAL_CATEGORIES and timely and written
        and str(account.get("status", "")).upper() == "OPEN"
        and account.get("standing_confirmed") is True
        and account.get("has_holds") is False and account.get("has_restrictions") is False
        and dispute.get("pin_compromised") != "yes_shared"
    )
    if dispute.get("pin_compromised") == "yes_shared":
        warnings.append("Voluntary PIN sharing means provisional credit is not required.")

    action = ACTION_BY_CATEGORY.get(category)
    categories = case.get("same_card_categories", [category])
    if not isinstance(categories, list) or any(item not in ACTION_BY_CATEGORY for item in categories):
        errors.append("same_card_categories must contain valid categories for disputes being filed on this card.")
        categories = [category] if action else []
    all_actions = [ACTION_BY_CATEGORY[item] for item in categories]
    post_action = max(all_actions, key=lambda item: SEVERITY[item]) if all_actions else None

    affidavit_required = bool(amount is not None and amount > 200)
    if affidavit_required:
        warnings.append("EFT Error Resolution Affidavit is required: email it and obtain return within 10 business days.")
    if owner == "third_party":
        investigation_days = 90
        provisional_deadline = 20 if new_account else 10
    else:
        foreign_pos = case.get("international_or_foreign_pos") is True
        investigation_days = 90 if new_account or foreign_pos else 45
        provisional_deadline = 20 if new_account else 10
    immediate_credit = bool(owner == "rho_bank" and journal_outcome == "confirmed_discrepancy")

    valid = not errors
    payload = None
    if valid:
        payload = {
            "transaction_id": tx["transaction_id"], "account_id": account_id,
            "card_id": card["card_id"], "user_id": user_id,
            "dispute_category": category, "transaction_date": dispute["transaction_date"],
            "discovery_date": dispute["discovery_date"], "disputed_amount": amount,
            "transaction_type": transaction_type,
            "card_in_possession": dispute["card_in_possession"],
            "pin_compromised": dispute["pin_compromised"],
            "contacted_merchant": dispute["contacted_merchant"],
            "police_report_filed": dispute["police_report_filed"],
            "written_statement_provided": written,
            "provisional_credit_eligible": eligible,
            "card_action": action,
        }
    return {
        "valid": valid, "errors": errors, "warnings": warnings,
        "unresolved_disputes_on_account": unresolved_count,
        "account_dispute_limit": TIER_LIMITS.get(tier),
        "provisional_credit_eligible": eligible,
        "provisional_credit_deadline_business_days": provisional_deadline,
        "immediate_credit_due_if_supported": immediate_credit,
        "investigation_timeline_business_days": investigation_days,
        "affidavit_required": affidavit_required,
        "filing_payload": payload,
        "post_filing_card_action": post_action,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)], "warnings": [], "filing_payload": None}))
