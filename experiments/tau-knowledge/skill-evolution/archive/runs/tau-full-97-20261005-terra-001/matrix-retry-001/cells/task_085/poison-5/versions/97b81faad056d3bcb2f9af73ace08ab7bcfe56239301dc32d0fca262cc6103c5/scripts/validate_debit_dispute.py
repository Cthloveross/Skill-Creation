#!/usr/bin/env python3
"""Validate and plan a live ATM cash-discrepancy filing.

Input is one JSON object:
{
  "today": "MM/DD/YYYY",
  "reg_e_disclosure_given": true,
  "verified_identity_fields": ["date_of_birth", "address"],
  "identity_log_completed": true,
  "user_id": "live user ID",
  "account": {
    "account_id": "...", "account_type": "checking", "status": "OPEN",
    "belongs_to_user": true, "balance_verified": true,
    "account_class": "optional published tier label",
    "has_holds": false, "has_restrictions": false
  },
  "card": {"card_id": "...", "account_id": "...", "user_id": "...", "status": "ACTIVE"},
  "transaction": {
    "transaction_id": "...", "account_id": "...", "date": "MM/DD/YYYY",
    "amount": -300.0, "type": "atm_withdrawal", "matched_to_customer": true
  },
  "disputes": [{"account_id": "...", "status": "OPEN"}],
  "atm": {"owner": "rho_bank", "journal_outcome": "unavailable"},
  "statement_date": "MM/DD/YYYY (optional)",
  "dispute": {
    "transaction_date": "MM/DD/YYYY", "discovery_date": "MM/DD/YYYY",
    "disputed_amount": 100.0, "card_in_possession": true,
    "pin_compromised": "no", "contacted_merchant": false,
    "police_report_filed": false, "written_statement_provided": true
  }
}

All data must come from the current interaction and runtime lookup results. A missing
statement date does not invalidate filing; it yields false provisional-credit eligibility.
The script does not call tools and does not file a dispute.
"""
import json
import sys
from datetime import datetime, timedelta

UNRESOLVED = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
TIER_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}


def date(value, label, errors, optional=False):
    if value in (None, "") and optional:
        return None
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{label} must be a valid MM/DD/YYYY date.")
        return None


def boolean(obj, key, errors, prefix=""):
    value = obj.get(key)
    if not isinstance(value, bool):
        errors.append(f"{prefix}{key} must be boolean.")
        return False
    return value


def positive_number(value, label, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be numeric.")
        return None
    return float(value)


def tier_key(value):
    text = str(value or "").strip().lower()
    return text.replace(" tier", "")


def main(case):
    errors, warnings = [], []
    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    card = case.get("card") if isinstance(case.get("card"), dict) else {}
    tx = case.get("transaction") if isinstance(case.get("transaction"), dict) else {}
    dispute = case.get("dispute") if isinstance(case.get("dispute"), dict) else {}
    atm = case.get("atm") if isinstance(case.get("atm"), dict) else {}

    today = date(case.get("today"), "today", errors)
    if not boolean(case, "reg_e_disclosure_given", errors):
        errors.append("Give the Regulation E reporting disclosure before filing.")
    fields = case.get("verified_identity_fields")
    accepted = {"date_of_birth", "address", "email", "phone_number"}
    if not isinstance(fields, list) or len(set(fields) & accepted) < 2:
        errors.append("Two verified identity fields are required.")
    if not boolean(case, "identity_log_completed", errors):
        errors.append("Successful identity verification must be logged before filing.")
    user_id = case.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        errors.append("A verified user_id is required.")

    account_id = account.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        errors.append("Selected account_id is required.")
    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("The selected account must be checking.")
    if str(account.get("status", "")).upper() != "OPEN":
        errors.append("The selected checking account must be OPEN.")
    if not boolean(account, "belongs_to_user", errors, "account."):
        errors.append("Account ownership must be confirmed.")
    if not boolean(account, "balance_verified", errors, "account."):
        errors.append("The returned account balance must be reviewed before filing.")

    disputes = case.get("disputes")
    if not isinstance(disputes, list):
        errors.append("disputes must be the user's dispute-status list.")
        disputes = []
    open_count = sum(
        1 for item in disputes if isinstance(item, dict)
        and item.get("account_id") == account_id
        and str(item.get("status", "")).upper() in UNRESOLVED
    )
    tier = tier_key(account.get("account_class"))
    limit = TIER_LIMITS.get(tier)
    if limit is None:
        # Zero disputes is below every published maximum. For nonzero counts, use
        # the smallest published limit unless the actual tier is confirmed.
        limit = 2
        if open_count:
            warnings.append("Account label does not map to a published tier; applied conservative Entry limit.")
    if open_count >= limit:
        errors.append(f"Selected account has {open_count} unresolved disputes; applicable limit is {limit}.")

    card_id = card.get("card_id")
    if not isinstance(card_id, str) or not card_id:
        errors.append("A linked debit card_id is required.")
    if card.get("account_id") != account_id or card.get("user_id") != user_id:
        errors.append("Card must be linked to the selected account and verified user.")
    if str(card.get("status", "")).upper() == "CLOSED":
        errors.append("A closed historical debit card cannot be used.")

    if not isinstance(tx.get("transaction_id"), str) or not tx.get("transaction_id"):
        errors.append("A matched account-history transaction_id is required.")
    if tx.get("account_id") != account_id:
        errors.append("Transaction must belong to selected account.")
    if not boolean(tx, "matched_to_customer", errors, "transaction."):
        errors.append("Transaction must match the customer's date, ATM, and charged amount.")
    tx_date = date(tx.get("date"), "transaction.date", errors)
    tx_amount = positive_number(tx.get("amount"), "transaction.amount", errors)
    if str(tx.get("type", "")) != "atm_withdrawal":
        errors.append("Transaction must be an atm_withdrawal.")
    if tx_amount is not None and abs(tx_amount) < 1:
        errors.append("Transaction must be at least $1.00.")
    if today and tx_date:
        age = (today - tx_date).days
        if age < 0 or age > 60:
            errors.append("Transaction must be no more than 60 calendar days old.")

    filing_date = date(dispute.get("transaction_date"), "dispute.transaction_date", errors)
    discovery = date(dispute.get("discovery_date"), "dispute.discovery_date", errors)
    if tx_date and filing_date and tx_date != filing_date:
        errors.append("Dispute transaction date must match selected transaction.")
    if tx_date and discovery and discovery < tx_date:
        errors.append("Discovery date cannot precede transaction date.")
    amount = positive_number(dispute.get("disputed_amount"), "dispute.disputed_amount", errors)
    if amount is not None:
        if amount < 1:
            errors.append("Disputed shortage must be at least $1.00.")
        if tx_amount is not None and amount > abs(tx_amount):
            errors.append("Disputed shortage cannot exceed withdrawal amount.")
    in_possession = boolean(dispute, "card_in_possession", errors, "dispute.")
    pin = dispute.get("pin_compromised")
    if pin not in PIN_VALUES:
        errors.append("dispute.pin_compromised is invalid.")
    contacted = boolean(dispute, "contacted_merchant", errors, "dispute.")
    police = boolean(dispute, "police_report_filed", errors, "dispute.")
    written = boolean(dispute, "written_statement_provided", errors, "dispute.")

    owner = atm.get("owner")
    if owner not in {"rho_bank", "third_party"}:
        errors.append("ATM owner must be rho_bank or third_party.")
    journal = atm.get("journal_outcome")
    if owner == "rho_bank":
        if journal not in {"confirmed_discrepancy", "shows_requested_amount", "unavailable"}:
            errors.append("Rho-Bank ATM journal outcome is required.")
        elif journal == "shows_requested_amount":
            warnings.append("Journal does not validate the claim; formal filing remains permitted.")

    statement = date(case.get("statement_date"), "statement_date", errors, optional=True)
    timely = False
    if statement and discovery:
        timely = discovery <= statement + timedelta(days=60)
        if not timely:
            warnings.append("Statement-based timely reporting is not established.")
    else:
        warnings.append("Statement date unavailable: file if otherwise valid; required provisional credit is not established.")
    standing_known = account.get("has_holds") is False and account.get("has_restrictions") is False
    eligible = bool(timely and written and standing_known and pin != "yes_shared")
    if not standing_known:
        warnings.append("No-hold/no-restriction standing is not established; provisional-credit eligibility is false.")
    if pin == "yes_shared":
        warnings.append("Voluntary PIN sharing means provisional credit is not required.")

    valid = not errors
    payload = None
    if valid:
        payload = {
            "transaction_id": tx["transaction_id"], "account_id": account_id,
            "card_id": card_id, "user_id": user_id,
            "dispute_category": "atm_cash_discrepancy",
            "transaction_date": dispute["transaction_date"],
            "discovery_date": dispute["discovery_date"],
            "disputed_amount": amount, "transaction_type": "atm_withdrawal",
            "card_in_possession": in_possession, "pin_compromised": pin,
            "contacted_merchant": contacted, "police_report_filed": police,
            "written_statement_provided": written,
            "provisional_credit_eligible": eligible, "card_action": "keep_active",
        }
    return {
        "valid": valid, "errors": errors, "warnings": warnings,
        "unresolved_disputes_on_account": open_count,
        "account_dispute_limit": limit,
        "provisional_credit_eligible": eligible,
        "provisional_credit_timing_established": statement is not None,
        "immediate_credit_due_if_supported": owner == "rho_bank" and journal == "confirmed_discrepancy",
        "affidavit_required": bool(amount is not None and amount > 200),
        "investigation_timeline_business_days": 90 if owner == "third_party" else 45,
        "filing_payload": payload,
        "post_filing_card_action": "keep_active",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)], "warnings": [], "filing_payload": None}))
