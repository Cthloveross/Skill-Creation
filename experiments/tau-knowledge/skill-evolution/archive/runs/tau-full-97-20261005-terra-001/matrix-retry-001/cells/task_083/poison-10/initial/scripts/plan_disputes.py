#!/usr/bin/env python3
"""Validate debit-card dispute filing data and produce proposed tool arguments.

Input JSON schema (top level):
{
  "as_of_date": "MM/DD/YYYY", "identity_verified": bool, "user_id": str,
  "existing_disputes": [{"account_id": str, "status": str}, ...],
  "disputes": [{
    "account": {"account_id": str, "account_type": "checking", "account_class": str,
                "status": "OPEN", "date_opened": "MM/DD/YYYY",
                "has_hold_or_restriction": bool},
    "card": {"card_id": str, "account_id": str, "user_id": str, "status": str},
    "transaction": {"transaction_id": str, "account_id": str, "date": "MM/DD/YYYY",
                    "amount": number, "type": str, "status": str},
    "dispute_category": str, "discovery_date": "MM/DD/YYYY", "disputed_amount": number,
    "transaction_type": str, "card_in_possession": bool, "pin_compromised": str,
    "contacted_merchant": bool, "police_report_filed": bool,
    "written_statement_provided": bool, "timely_reporting": bool,
    "atm_owner": "rho_bank"|"third_party" (required for ATM categories),
    "affidavit_disclosure_given": bool (required disclosure flag for third-party ATM cash claims > 200),
    "duplicate_candidates": [{"transaction_id": str, "date": "MM/DD/YYYY"}, ...] (optional)
  }]
}

Output contains per-dispute errors, warnings, a strict provisional-credit decision,
proposed filing_args for ready cases, and most-severe recommended action per card.
"""
import json
import sys
from datetime import datetime

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
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
TIER_LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
SEVERITY = {"keep_active": 1, "freeze_pending_investigation": 2, "close_and_reissue": 3}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be an MM/DD/YYYY string")
    return datetime.strptime(value, "%m/%d/%Y").date()


def tier_of(value):
    text = str(value or "").upper().replace("_", " ").strip()
    for tier in TIER_LIMITS:
        if tier in text:
            return tier
    return None


def is_bool(obj, key):
    return key in obj and isinstance(obj[key], bool)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def required(case, key, errors):
    if key not in case or case[key] is None or case[key] == "":
        errors.append("Missing required filing field: " + key)
        return False
    return True


def provisional(case, account, category, errors):
    reasons = []
    missing = []
    for key in ("timely_reporting", "written_statement_provided", "contacted_merchant", "pin_compromised"):
        if key not in case:
            missing.append(key)
    if "has_hold_or_restriction" not in account:
        missing.append("account.has_hold_or_restriction")
    if missing:
        return False, ["cannot determine: missing " + ", ".join(missing)]
    if case["timely_reporting"] is not True:
        reasons.append("not confirmed timely within 60 days of the statement")
    if category not in PC_CATEGORIES:
        reasons.append("category is not a required provisional-credit category")
    if case["written_statement_provided"] is not True:
        reasons.append("written statement not provided")
    if str(account.get("status", "")).upper() != "OPEN" or account["has_hold_or_restriction"]:
        reasons.append("account is not OPEN without holds or restrictions")
    if case.get("pin_compromised") == "yes_shared":
        reasons.append("PIN was voluntarily shared")
    # Merchant contact is meaningful for merchant disputes, not ATM processing errors.
    merchant_categories = {"unauthorized_transaction", "duplicate_charge", "incorrect_amount",
                           "goods_services_not_received", "recurring_charge_after_cancellation"}
    if category in merchant_categories and category not in FRAUD_CATEGORIES and not case["contacted_merchant"]:
        reasons.append("merchant-resolution attempt not documented for non-fraud merchant dispute")
    try:
        account_age = (parse_date(GLOBAL_AS_OF) - parse_date(account.get("date_opened"))).days
        if account_age < 30 and category == "card_not_present_fraud":
            reasons.append("new account card-not-present exception")
    except (ValueError, TypeError):
        reasons.append("cannot determine account age")
    return not reasons, reasons


def check_earliest_duplicate(case, transaction_id, errors):
    candidates = case.get("duplicate_candidates")
    if not candidates:
        return
    parsed = []
    for c in candidates:
        try:
            parsed.append((parse_date(c.get("date")), c.get("transaction_id")))
        except (ValueError, TypeError):
            errors.append("duplicate_candidates contains a missing or invalid date")
            return
    if not parsed:
        return
    earliest_date = min(item[0] for item in parsed)
    earliest_ids = {item[1] for item in parsed if item[0] == earliest_date}
    if transaction_id not in earliest_ids:
        errors.append("Duplicate-charge policy requires selecting the earliest duplicate transaction")
    elif len(earliest_ids) > 1:
        errors.append("Multiple duplicates share the earliest date; identify the first transaction before filing")


def process(case, top, used_by_account):
    errors, warnings = [], []
    account = case.get("account") if isinstance(case.get("account"), dict) else {}
    card = case.get("card") if isinstance(case.get("card"), dict) else {}
    tx = case.get("transaction") if isinstance(case.get("transaction"), dict) else {}
    category = case.get("dispute_category")

    if top.get("identity_verified") is not True:
        errors.append("Customer identity/authority has not been verified")
    if not isinstance(top.get("user_id"), str) or not top.get("user_id"):
        errors.append("Missing verified user_id")
    for key in ("transaction_id", "account_id", "date", "amount"):
        if key not in tx:
            errors.append("Missing transaction." + key)
    for key in ("account_id", "account_type", "account_class", "status"):
        if key not in account:
            errors.append("Missing account." + key)
    for key in ("card_id", "account_id", "user_id"):
        if key not in card:
            errors.append("Missing card." + key)

    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("Linked account is not a checking account")
    if str(account.get("status", "")).upper() != "OPEN":
        errors.append("Linked checking account is not OPEN")
    if account.get("account_id") != tx.get("account_id"):
        errors.append("Transaction is not linked to the selected checking account")
    if card.get("account_id") != account.get("account_id"):
        errors.append("Card is not linked to the selected checking account")
    if card.get("user_id") != top.get("user_id"):
        errors.append("Cardholder does not match verified user")

    tier = tier_of(account.get("account_class"))
    if not tier:
        errors.append("Unsupported or missing checking account tier")
    else:
        account_id = account.get("account_id")
        if used_by_account.get(account_id, 0) >= TIER_LIMITS[tier]:
            errors.append("Open-dispute limit would be exceeded for this account tier")

    if category not in CATEGORIES:
        errors.append("Invalid dispute_category")
    if case.get("transaction_type") not in TRANSACTION_TYPES:
        errors.append("Invalid transaction_type")
    if case.get("pin_compromised") not in PIN_VALUES:
        errors.append("Invalid pin_compromised value")
    for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not is_bool(case, key):
            errors.append("Missing or non-boolean field: " + key)

    for key in ("discovery_date", "disputed_amount"):
        required(case, key, errors)
    try:
        as_of = parse_date(GLOBAL_AS_OF)
        tx_date = parse_date(tx.get("date"))
        parse_date(case.get("discovery_date"))
        age = (as_of - tx_date).days
        if age < 0 or age > 60:
            errors.append("Transaction is not within the required 60-day filing window")
    except (ValueError, TypeError):
        errors.append("Transaction date, discovery date, or as_of_date is invalid")
    if not number(tx.get("amount")) or abs(float(tx.get("amount", 0))) < 1:
        errors.append("Transaction must be at least $1.00")
    if not number(case.get("disputed_amount")) or float(case.get("disputed_amount", 0)) <= 0:
        errors.append("Disputed amount must be a positive number")
    elif number(tx.get("amount")) and float(case["disputed_amount"]) > abs(float(tx["amount"])):
        errors.append("Disputed amount cannot exceed the transaction amount")

    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        if case.get("atm_owner") not in {"rho_bank", "third_party"}:
            errors.append("ATM owner must be rho_bank or third_party")
        if (category == "atm_cash_discrepancy" and case.get("atm_owner") == "third_party"
                and number(case.get("disputed_amount")) and float(case["disputed_amount"]) > 200):
            if case.get("affidavit_disclosure_given") is not True:
                warnings.append("Give and record the required third-party ATM affidavit disclosure before completion")
    if category == "duplicate_charge":
        check_earliest_duplicate(case, tx.get("transaction_id"), errors)
    if category in FRAUD_CATEGORIES and number(case.get("disputed_amount")) and float(case["disputed_amount"]) > 500:
        if case.get("police_report_filed") is not True:
            warnings.append("Recommend a police report for fraud over $500")

    pc_eligible, pc_reasons = provisional(case, account, category, errors)
    if not pc_eligible:
        warnings.append("Provisional credit not required: " + "; ".join(pc_reasons))

    action = ACTIONS.get(category)
    ready = not errors
    filing_args = None
    if ready:
        filing_args = {
            "transaction_id": tx["transaction_id"], "account_id": account["account_id"],
            "card_id": card["card_id"], "user_id": top["user_id"],
            "dispute_category": category, "transaction_date": tx["date"],
            "discovery_date": case["discovery_date"], "disputed_amount": float(case["disputed_amount"]),
            "transaction_type": case["transaction_type"],
            "card_in_possession": case["card_in_possession"], "pin_compromised": case["pin_compromised"],
            "contacted_merchant": case["contacted_merchant"],
            "police_report_filed": case["police_report_filed"],
            "written_statement_provided": case["written_statement_provided"],
            "provisional_credit_eligible": pc_eligible, "card_action": action,
        }
        used_by_account[account["account_id"]] = used_by_account.get(account["account_id"], 0) + 1
    return {"ready_to_file": ready, "errors": errors, "warnings": warnings,
            "provisional_credit_eligible": pc_eligible, "card_action": action,
            "filing_args": filing_args, "card_id": card.get("card_id")}


def main(data):
    global GLOBAL_AS_OF
    GLOBAL_AS_OF = data.get("as_of_date")
    try:
        parse_date(GLOBAL_AS_OF)
    except (ValueError, TypeError):
        return {"ok": False, "error": "as_of_date must be MM/DD/YYYY"}
    if not isinstance(data.get("existing_disputes"), list) or not isinstance(data.get("disputes"), list):
        return {"ok": False, "error": "existing_disputes and disputes must be lists"}
    used = {}
    for dispute in data["existing_disputes"]:
        if isinstance(dispute, dict) and str(dispute.get("status", "")).upper() in OPEN_STATUSES:
            aid = dispute.get("account_id")
            if aid:
                used[aid] = used.get(aid, 0) + 1
    results = [process(case if isinstance(case, dict) else {}, data, used) for case in data["disputes"]]
    actions = {}
    for result in results:
        if result["ready_to_file"] and result["card_id"]:
            current = actions.get(result["card_id"])
            if current is None or SEVERITY[result["card_action"]] > SEVERITY[current]:
                actions[result["card_id"]] = result["card_action"]
    return {"ok": True, "results": results,
            "post_filing_most_severe_card_action": actions,
            "note": "Recommendations do not execute banking actions; recheck live prerequisites before each action."}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
