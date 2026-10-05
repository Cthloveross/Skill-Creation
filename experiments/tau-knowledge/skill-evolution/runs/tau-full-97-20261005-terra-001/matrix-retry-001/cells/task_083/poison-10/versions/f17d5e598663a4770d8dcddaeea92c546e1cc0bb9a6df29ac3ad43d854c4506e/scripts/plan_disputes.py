#!/usr/bin/env python3
"""Preflight debit-card dispute cases without performing banking actions.

Read one JSON object from stdin and emit one JSON object on stdout.

Top-level input fields:
  as_of_date: MM/DD/YYYY
  identity_verified: boolean
  user_id: verified customer ID
  existing_disputes: [{account_id, status}, ...]
  disputes: [case, ...]

Each case has account, card, transaction, classification, and intake fields described
in SKILL.md. ATM cases require atm_owner. Third-party ATM cash discrepancies whose
*disputed amount* exceeds 200 require affidavit_disclosure_given: true. Optional
charged_amount and cash_dispensed are validated against disputed_amount. This script
never calls a bank tool, files a dispute, or changes a card.
"""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TX_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
TIER_LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
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
SEVERITY = {"keep_active": 1, "freeze_pending_investigation": 2, "close_and_reissue": 3}
PROVISIONAL_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
MERCHANT_CATEGORIES = {
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation",
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be MM/DD/YYYY")
    return datetime.strptime(value, "%m/%d/%Y").date()


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def account_tier(value):
    text = str(value or "").upper().replace("_", " ")
    return next((tier for tier in TIER_LIMITS if tier in text), None)


def require_bool(case, key, errors):
    if not isinstance(case.get(key), bool):
        errors.append("Missing or non-boolean field: " + key)


def provisional_decision(case, account, category, as_of):
    required = ["timely_reporting", "written_statement_provided", "pin_compromised"]
    missing = [key for key in required if key not in case]
    if "has_hold_or_restriction" not in account:
        missing.append("account.has_hold_or_restriction")
    if missing:
        return False, "cannot determine: missing " + ", ".join(missing)

    reasons = []
    if case["timely_reporting"] is not True:
        reasons.append("timely statement reporting is not confirmed")
    if category not in PROVISIONAL_CATEGORIES:
        reasons.append("category is not a required provisional-credit category")
    if case["written_statement_provided"] is not True:
        reasons.append("written statement not provided")
    if str(account.get("status", "")).upper() != "OPEN" or account["has_hold_or_restriction"]:
        reasons.append("account is not OPEN without holds or restrictions")
    if case.get("pin_compromised") == "yes_shared":
        reasons.append("PIN was voluntarily shared")
    if category in MERCHANT_CATEGORIES and case.get("contacted_merchant") is not True:
        reasons.append("merchant-resolution attempt not documented")
    try:
        if category == "card_not_present_fraud" and (as_of - parse_date(account.get("date_opened"))).days < 30:
            reasons.append("new-account card-not-present exception")
    except (TypeError, ValueError):
        reasons.append("cannot determine account age")
    return not reasons, "; ".join(reasons)


def check_atm_shortage(case, category, errors):
    """Validate supplied cash details and apply affidavit threshold to the shortage."""
    if category != "atm_cash_discrepancy":
        return None
    charged = case.get("charged_amount")
    dispensed = case.get("cash_dispensed")
    if charged is None and dispensed is None:
        return None
    if not number(charged) or not number(dispensed):
        errors.append("charged_amount and cash_dispensed must both be numeric when supplied")
        return None
    shortage = float(charged) - float(dispensed)
    if shortage <= 0:
        errors.append("ATM cash discrepancy requires a positive cash shortage")
    elif number(case.get("disputed_amount")) and abs(float(case["disputed_amount"]) - shortage) > 0.000001:
        errors.append("disputed_amount must equal charged_amount minus cash_dispensed")
    return shortage


def process(case, top, usage, as_of):
    errors, warnings = [], []
    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    card = case.get("card") if isinstance(case.get("card"), dict) else {}
    tx = case.get("transaction") if isinstance(case.get("transaction"), dict) else {}
    category = case.get("dispute_category")

    if top.get("identity_verified") is not True:
        errors.append("Customer identity and authority have not been verified")
    if not isinstance(top.get("user_id"), str) or not top["user_id"]:
        errors.append("Missing verified user_id")
    for key in ("account_id", "account_type", "account_class", "status", "date_opened", "has_hold_or_restriction"):
        if key not in account:
            errors.append("Missing account." + key)
    for key in ("card_id", "account_id", "user_id"):
        if key not in card:
            errors.append("Missing card." + key)
    for key in ("transaction_id", "account_id", "date", "amount"):
        if key not in tx:
            errors.append("Missing transaction." + key)

    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("Linked account is not checking")
    if str(account.get("status", "")).upper() != "OPEN":
        errors.append("Linked checking account is not OPEN")
    if account.get("account_id") != card.get("account_id"):
        errors.append("Card is not linked to selected account")
    if account.get("account_id") != tx.get("account_id"):
        errors.append("Transaction is not linked to selected account")
    if card.get("user_id") != top.get("user_id"):
        errors.append("Cardholder does not match verified user")

    tier = account_tier(account.get("account_class"))
    if not tier:
        errors.append("Unsupported or missing checking account tier")
    elif usage.get(account.get("account_id"), 0) >= TIER_LIMITS[tier]:
        errors.append("Open-dispute limit would be exceeded for this account")

    if category not in CATEGORIES:
        errors.append("Invalid dispute_category")
    if case.get("transaction_type") not in TX_TYPES:
        errors.append("Invalid transaction_type")
    if case.get("pin_compromised") not in PIN_VALUES:
        errors.append("Invalid pin_compromised value")
    for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        require_bool(case, key, errors)
    if not isinstance(case.get("discovery_date"), str):
        errors.append("Missing discovery_date")
    if not number(case.get("disputed_amount")) or float(case.get("disputed_amount", 0)) <= 0:
        errors.append("disputed_amount must be a positive number")
    if not number(tx.get("amount")) or abs(float(tx.get("amount", 0))) < 1:
        errors.append("Transaction must be at least $1.00")
    if number(tx.get("amount")) and number(case.get("disputed_amount")) and float(case["disputed_amount"]) > abs(float(tx["amount"])):
        errors.append("Disputed amount cannot exceed transaction amount")
    try:
        age = (as_of - parse_date(tx.get("date"))).days
        parse_date(case.get("discovery_date"))
        if age < 0 or age > 60:
            errors.append("Transaction is outside the 60-day filing window")
    except (TypeError, ValueError):
        errors.append("Invalid transaction, discovery, or as-of date")

    shortage = check_atm_shortage(case, category, errors)
    affidavit_required = False
    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        if case.get("atm_owner") not in {"rho_bank", "third_party"}:
            errors.append("ATM owner must be rho_bank or third_party")
        # The threshold is the actual claim/shortage, not the gross withdrawal.
        claim_amount = shortage if shortage is not None else case.get("disputed_amount")
        affidavit_required = (
            category == "atm_cash_discrepancy"
            and case.get("atm_owner") == "third_party"
            and number(claim_amount)
            and float(claim_amount) > 200
        )
        if affidavit_required and case.get("affidavit_disclosure_given") is not True:
            errors.append("Required third-party ATM affidavit disclosure has not been recorded")

    if category == "duplicate_charge" and case.get("duplicate_candidates"):
        try:
            candidates = [(parse_date(item["date"]), item["transaction_id"]) for item in case["duplicate_candidates"]]
            earliest = min(day for day, _ in candidates)
            earliest_ids = {ident for day, ident in candidates if day == earliest}
            if tx.get("transaction_id") not in earliest_ids:
                errors.append("Duplicate-charge policy requires the earliest duplicate")
            elif len(earliest_ids) > 1:
                errors.append("Identify the first transaction among same-day earliest duplicates")
        except (KeyError, TypeError, ValueError):
            errors.append("Invalid duplicate_candidates")

    if category in {"card_present_fraud", "card_not_present_fraud"} and number(case.get("disputed_amount")) and float(case["disputed_amount"]) > 500 and case.get("police_report_filed") is not True:
        warnings.append("Recommend a police report for fraud over $500")

    eligible, rationale = provisional_decision(case, account, category, as_of)
    if not eligible:
        warnings.append("Provisional credit not required: " + rationale)

    action = CARD_ACTIONS.get(category)
    ready = not errors
    filing_args = None
    if ready:
        filing_args = {
            "transaction_id": tx["transaction_id"],
            "account_id": account["account_id"],
            "card_id": card["card_id"],
            "user_id": top["user_id"],
            "dispute_category": category,
            "transaction_date": tx["date"],
            "discovery_date": case["discovery_date"],
            "disputed_amount": float(case["disputed_amount"]),
            "transaction_type": case["transaction_type"],
            "card_in_possession": case["card_in_possession"],
            "pin_compromised": case["pin_compromised"],
            "contacted_merchant": case["contacted_merchant"],
            "police_report_filed": case["police_report_filed"],
            "written_statement_provided": case["written_statement_provided"],
            "provisional_credit_eligible": eligible,
            "card_action": action,
        }
        usage[account["account_id"]] = usage.get(account["account_id"], 0) + 1

    return {
        "ready_to_file": ready,
        "errors": errors,
        "warnings": warnings,
        "provisional_credit_eligible": eligible,
        "card_action": action,
        "affidavit_required": affidavit_required,
        "filing_args": filing_args,
        "card_id": card.get("card_id"),
    }


def main(data):
    try:
        as_of = parse_date(data.get("as_of_date"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "as_of_date must be MM/DD/YYYY"}
    if not isinstance(data.get("existing_disputes"), list) or not isinstance(data.get("disputes"), list):
        return {"ok": False, "error": "existing_disputes and disputes must be lists"}

    usage = {}
    for item in data["existing_disputes"]:
        if isinstance(item, dict) and str(item.get("status", "")).upper() in OPEN_STATUSES and item.get("account_id"):
            usage[item["account_id"]] = usage.get(item["account_id"], 0) + 1

    results = [process(item if isinstance(item, dict) else {}, data, usage, as_of) for item in data["disputes"]]
    severe_actions = {}
    for result in results:
        card_id, action = result.get("card_id"), result.get("card_action")
        if result["ready_to_file"] and card_id and action:
            current = severe_actions.get(card_id)
            if current is None or SEVERITY[action] > SEVERITY[current]:
                severe_actions[card_id] = action
    return {
        "ok": True,
        "results": results,
        "post_filing_most_severe_card_action": severe_actions,
        "note": "Checklist only: recheck live prerequisites and file through normal banking tools.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True, separators=(",", ":")))
