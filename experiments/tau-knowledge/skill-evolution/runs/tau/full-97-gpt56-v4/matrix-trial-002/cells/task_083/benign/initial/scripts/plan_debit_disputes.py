#!/usr/bin/env python3
"""Validate and plan debit-card dispute filings.

Input: JSON object described in SKILL.md on stdin.
Output: JSON object containing errors, warnings, per-dispute filing readiness,
and post-filing card actions. This is advisory only and has no bank side effects.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, date

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ACTIVE = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTION = {
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


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{label} must be a valid MM/DD/YYYY date.")
        return None


def b(value, label, errors):
    if type(value) is not bool:
        errors.append(f"{label} must be boolean.")
        return None
    return value


def active_count(existing, account_id):
    if not isinstance(existing, list):
        return None
    return sum(1 for x in existing if isinstance(x, dict) and x.get("account_id") == account_id
               and x.get("status") in ACTIVE)


def provisional(d, account, as_of, errors, warnings):
    category = d.get("category")
    timely = d.get("reported_within_60_days_of_statement")
    statement = b(timely, "reported_within_60_days_of_statement", errors)
    written = b(d.get("written_statement_provided"), "written_statement_provided", errors)
    no_holds = account.get("has_holds_or_restrictions") is False
    if "has_holds_or_restrictions" not in account or type(account.get("has_holds_or_restrictions")) is not bool:
        errors.append("account.has_holds_or_restrictions must be boolean for provisional-credit decision.")
    opened = parse_date(account.get("date_opened"), "account.date_opened", errors)
    age = (as_of - opened).days if opened else None
    new_account = age is not None and age < 30

    blockers = []
    if statement is not True:
        blockers.append("timely reporting within 60 days of statement is not established")
    if category not in PC_CATEGORIES:
        blockers.append("category is not provisionally-credit-eligible")
    if written is not True:
        blockers.append("written statement not provided")
    if account.get("status") != "OPEN" or not no_holds:
        blockers.append("account is not open and unrestricted")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and d.get("contacted_merchant") is False:
        blockers.append("merchant was not contacted for non-fraud dispute")
    if d.get("pin_compromised") == "yes_shared":
        blockers.append("PIN was voluntarily shared")
    if new_account and category == "card_not_present_fraud":
        blockers.append("new-account card-not-present exclusion")

    eligible = not blockers and not errors
    if eligible:
        warnings.append("Eligible only from supplied facts; issue timing is %s business days." % (20 if new_account else 10))
    return {
        "eligible": eligible,
        "blockers": blockers,
        "issue_within_business_days": 20 if new_account else 10,
        "investigation_business_days": 90 if new_account or d.get("international_or_out_of_us_pos") is True else 45,
    }


def validate_one(d, root, index, planned_per_account):
    errors, warnings = [], []
    account = root.get("account") if isinstance(root.get("account"), dict) else {}
    as_of = root["_as_of"]
    required = ["transaction_id", "account_id", "card_id", "user_id", "transaction_date",
                "discovery_date", "category", "transaction_type"]
    for key in required:
        if not d.get(key):
            errors.append(f"{key} is required.")
    tx_date = parse_date(d.get("transaction_date"), "transaction_date", errors)
    discovery = parse_date(d.get("discovery_date"), "discovery_date", errors)
    if tx_date and tx_date > as_of:
        errors.append("transaction_date cannot be in the future.")
    if discovery and discovery > as_of:
        errors.append("discovery_date cannot be in the future.")
    if tx_date and discovery and discovery < tx_date:
        warnings.append("Discovery date precedes transaction date; confirm this is accurate.")
    if tx_date and (as_of - tx_date).days > 60:
        errors.append("Transaction is more than 60 days old.")

    category = d.get("category")
    if category not in CATEGORIES:
        errors.append("category is not an allowed dispute category.")
    if d.get("transaction_type") not in TYPES:
        errors.append("transaction_type is not allowed.")
    if category == "atm_cash_discrepancy" and d.get("transaction_type") != "atm_withdrawal":
        errors.append("ATM cash discrepancy requires transaction_type atm_withdrawal.")
    if category == "atm_deposit_not_credited" and d.get("transaction_type") != "atm_deposit":
        errors.append("ATM deposit-not-credited requires transaction_type atm_deposit.")

    for key in ("transaction_amount", "disputed_amount"):
        if type(d.get(key)) not in (int, float) or isinstance(d.get(key), bool):
            errors.append(f"{key} must be a numeric dollar value.")
    tx_amount, disputed = d.get("transaction_amount"), d.get("disputed_amount")
    if isinstance(tx_amount, (int, float)) and not isinstance(tx_amount, bool) and tx_amount >= -1:
        errors.append("transaction_amount must be an account-history debit of at least $1 (negative value).")
    if isinstance(disputed, (int, float)) and not isinstance(disputed, bool):
        if disputed < 1:
            errors.append("disputed_amount must be at least $1.")
        if isinstance(tx_amount, (int, float)) and not isinstance(tx_amount, bool) and disputed > abs(tx_amount):
            errors.append("disputed_amount cannot exceed the transaction debit.")

    for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        b(d.get(key), key, errors)
    if d.get("pin_compromised") not in PINS:
        errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown.")
    fraud = b(d.get("fraud_suspected"), "fraud_suspected", errors)
    if fraud is True and category not in {"card_present_fraud", "card_not_present_fraud"}:
        errors.append("Suspected fraud must use a card-present or card-not-present fraud category.")
    if fraud is False and category in {"card_present_fraud", "card_not_present_fraud"}:
        errors.append("Fraud category conflicts with fraud_suspected=false.")
    if category == "card_present_fraud" and d.get("transaction_type") not in {"pin_purchase", "signature_purchase"}:
        errors.append("card_present_fraud needs a physical purchase transaction type.")
    if category == "card_not_present_fraud" and d.get("transaction_type") != "online_purchase":
        errors.append("card_not_present_fraud requires online_purchase.")
    if category.startswith("atm_"):
        atm = b(d.get("rho_bank_atm"), "rho_bank_atm", errors)
        if category == "atm_cash_discrepancy" and atm is False and isinstance(disputed, (int, float)) and disputed > 200:
            warnings.append("Third-party ATM discrepancy over $200: affidavit notice and return tracking are required.")

    if category == "duplicate_charge":
        candidates = d.get("duplicate_candidates")
        if not isinstance(candidates, list) or not candidates:
            errors.append("duplicate_candidates must identify all matching duplicate transaction records.")
        else:
            dated = []
            for c in candidates:
                if not isinstance(c, dict):
                    errors.append("Each duplicate candidate must be an object.")
                    continue
                cd = parse_date(c.get("transaction_date"), "duplicate candidate transaction_date", errors)
                if cd and c.get("transaction_id"):
                    dated.append((cd, c["transaction_id"]))
            if dated and d.get("transaction_id") != min(dated)[1]:
                errors.append("Duplicate dispute must use the earliest matching transaction_id.")

    if root.get("verified") is not True:
        errors.append("Customer verification must be logged before filing.")
    if account.get("account_type", "").lower() != "checking" or account.get("status") != "OPEN":
        errors.append("A linked OPEN checking account is required.")
    if d.get("account_id") != account.get("account_id"):
        errors.append("Dispute account_id does not match the qualified checking account.")

    capacity = root.get("_capacity")
    existing = active_count(root.get("existing_disputes"), d.get("account_id"))
    if existing is None:
        errors.append("existing_disputes must be a list to check account capacity.")
    elif capacity is not None and existing + planned_per_account[d.get("account_id")] > capacity:
        errors.append("Batch exceeds this account's active-dispute limit.")

    pc = provisional(d, account, as_of, errors, warnings)
    action = ACTION.get(category)
    return {
        "index": index,
        "transaction_id": d.get("transaction_id"),
        "account_id": d.get("account_id"),
        "card_id": d.get("card_id"),
        "ready_to_file": not errors,
        "errors": errors,
        "warnings": warnings,
        "card_action": action,
        "provisional_credit": pc,
    }


def main(payload):
    root_errors = []
    root = dict(payload) if isinstance(payload, dict) else {}
    as_of = parse_date(root.get("as_of"), "as_of", root_errors)
    root["_as_of"] = as_of or date.min
    account = root.get("account") if isinstance(root.get("account"), dict) else {}
    tier = str(account.get("account_class", "")).strip().lower().replace(" tier", "")
    root["_capacity"] = LIMITS.get(tier)
    if root["_capacity"] is None:
        root_errors.append("account.account_class must be Entry, Mid, Premium, or Elite.")
    disputes = root.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        root_errors.append("disputes must be a non-empty list.")
        disputes = []
    planned = Counter(d.get("account_id") for d in disputes if isinstance(d, dict))
    plans = [validate_one(d, root, i, planned) if isinstance(d, dict) else {
        "index": i, "ready_to_file": False, "errors": ["Dispute must be an object."], "warnings": [],
        "card_action": None, "provisional_credit": None
    } for i, d in enumerate(disputes)]
    actions = defaultdict(lambda: "keep_active")
    for p in plans:
        if p["ready_to_file"] and p.get("card_id") and p.get("card_action"):
            if SEVERITY[p["card_action"]] > SEVERITY[actions[p["card_id"]]]:
                actions[p["card_id"]] = p["card_action"]
    return {
        "ready_to_file": not root_errors and bool(plans) and all(p["ready_to_file"] for p in plans),
        "root_errors": root_errors,
        "disputes": plans,
        "post_filing_card_actions": [{"card_id": card, "action": action} for card, action in sorted(actions.items())],
        "note": "Advisory output only; execute banking tools separately after reviewing live records."
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ready_to_file": False, "root_errors": [f"Invalid JSON: {exc.msg}"]}))
        sys.exit(2)
