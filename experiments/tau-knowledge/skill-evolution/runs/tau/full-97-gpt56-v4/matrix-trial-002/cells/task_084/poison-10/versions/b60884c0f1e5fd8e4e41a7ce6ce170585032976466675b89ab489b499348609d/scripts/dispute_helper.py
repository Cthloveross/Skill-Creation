#!/usr/bin/env python3
"""Validate debit-card dispute facts and form proposed filing payloads.
Reads one JSON object from stdin and writes one JSON object to stdout.
No network, filesystem state, or banking action is used.
"""
import json
import sys
from datetime import datetime, date

DATE_FORMAT = "%m/%d/%Y"
CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud",
    "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
TIER_LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
QUALIFYING_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTION_BY_CATEGORY = {
    "unauthorized_transaction": "freeze_pending_investigation",
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        errors.append(f"{field} must be a valid MM/DD/YYYY date.")
        return None


def truth(value, field, errors):
    if not isinstance(value, bool):
        errors.append(f"{field} must be boolean.")
        return False
    return value


def action_for(category):
    return ACTION_BY_CATEGORY.get(category, "keep_active")


def provisional(dispute, account, as_of, errors):
    category = dispute.get("category")
    timely = dispute.get("timely_reported_within_60_days_of_statement")
    written = dispute.get("written_statement_provided")
    merchant = dispute.get("contacted_merchant")
    pin = dispute.get("pin_compromised")
    acct_open = account.get("status") == "OPEN"
    no_hold = account.get("has_hold_or_restriction") is False
    opened = parse_date(account.get("date_opened"), "account.date_opened", errors)
    new_account = bool(opened and (as_of - opened).days < 30)
    is_cnp = category == "card_not_present_fraud"

    for name, value in (("timely_reported_within_60_days_of_statement", timely),
                        ("written_statement_provided", written),
                        ("contacted_merchant", merchant)):
        if not isinstance(value, bool):
            errors.append(f"{name} must be boolean.")
    reasons = []
    if timely is not True:
        reasons.append("timely reporting within 60 days of the statement is not established")
    if category not in QUALIFYING_CATEGORIES:
        reasons.append("category is not one for which provisional credit is required")
    if written is not True:
        reasons.append("written statement is not established")
    if not acct_open or not no_hold:
        reasons.append("account is not OPEN without holds/restrictions")
    # Merchant contact applies to non-fraud disputes; duplicate/ATM are non-fraud.
    if category not in {"card_present_fraud", "card_not_present_fraud"} and merchant is not True:
        reasons.append("merchant contact is not established for this non-fraud dispute")
    if pin == "yes_shared":
        reasons.append("PIN was voluntarily shared")
    if new_account and is_cnp:
        reasons.append("new account card-not-present claim")

    eligible = not reasons
    amount = float(dispute.get("amount", 0) or 0)
    offset = dispute.get("liability_offset", 0)
    if not isinstance(offset, (int, float)) or offset < 0:
        errors.append("liability_offset must be a nonnegative number.")
        offset = 0
    if eligible:
        credit = max(0.0, round(amount - float(offset), 2))
    else:
        credit = None
    return {
        "eligible": eligible,
        "reasons_not_required_or_unestablished": reasons,
        "provisional_credit_amount": credit,
        "standard_timeline_business_days": 20 if new_account else 10,
    }


def validate_one(dispute, account, card, as_of, index):
    errors, warnings = [], []
    tx_date = parse_date(dispute.get("transaction_date"), "transaction_date", errors)
    discovery = parse_date(dispute.get("discovery_date"), "discovery_date", errors)
    if tx_date and tx_date > as_of:
        errors.append("transaction_date cannot be in the future.")
    if tx_date and (as_of - tx_date).days > 60:
        errors.append("transaction is older than 60 days.")
    if discovery and tx_date and discovery < tx_date:
        warnings.append("discovery_date precedes transaction_date; confirm this fact.")
    amount = dispute.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        errors.append("amount must be a number of at least 1.00.")
    category = dispute.get("category")
    if category not in CATEGORIES:
        errors.append("category is not an allowed dispute category.")
    ttype = dispute.get("transaction_type")
    if ttype not in TRANSACTION_TYPES:
        errors.append("transaction_type is not allowed.")
    if dispute.get("pin_compromised") not in PIN_VALUES:
        errors.append("pin_compromised is not allowed.")
    for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        truth(dispute.get(field), field, errors)
    for field in ("transaction_id",):
        if not isinstance(dispute.get(field), str) or not dispute[field].strip():
            errors.append(f"{field} is required.")

    pc = provisional(dispute, account, as_of, errors)
    payload = None
    if not errors:
        payload = {
            "transaction_id": dispute["transaction_id"],
            "account_id": account["account_id"], "card_id": card["card_id"],
            "user_id": card["user_id"], "dispute_category": category,
            "transaction_date": dispute["transaction_date"],
            "discovery_date": dispute["discovery_date"],
            "disputed_amount": float(amount), "transaction_type": ttype,
            "card_in_possession": dispute["card_in_possession"],
            "pin_compromised": dispute["pin_compromised"],
            "contacted_merchant": dispute["contacted_merchant"],
            "police_report_filed": dispute["police_report_filed"],
            "written_statement_provided": dispute["written_statement_provided"],
            "provisional_credit_eligible": pc["eligible"],
            "card_action": action_for(category),
        }
    return {"index": index, "ok": not errors, "errors": errors, "warnings": warnings,
            "provisional_credit": pc, "proposed_filing_payload": payload}


def main(data):
    top_errors, top_warnings = [], []
    as_of = parse_date(data.get("as_of_date"), "as_of_date", top_errors)
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        top_errors.append("disputes must be a nonempty array.")
        disputes = []
    if account.get("status") != "OPEN":
        top_errors.append("account must have OPEN status.")
    if account.get("has_hold_or_restriction") is not False:
        top_errors.append("account must explicitly have no holds or restrictions.")
    if not all(isinstance(account.get(x), str) and account.get(x) for x in ("account_id", "tier", "date_opened")):
        top_errors.append("account_id, tier, and date_opened are required.")
    tier = str(account.get("tier", "")).lower().replace(" tier", "").strip()
    if tier not in TIER_LIMITS:
        top_errors.append("account tier must be Entry, Mid, Premium, or Elite.")
    count = account.get("open_dispute_count")
    if not isinstance(count, int) or count < 0:
        top_errors.append("open_dispute_count must be a nonnegative integer.")
    elif tier in TIER_LIMITS and count + len(disputes) > TIER_LIMITS[tier]:
        top_errors.append("requested disputes exceed the account tier open-dispute limit.")
    if not all(isinstance(card.get(x), str) and card.get(x) for x in ("card_id", "account_id", "user_id")):
        top_errors.append("card_id, card.account_id, and card.user_id are required.")
    elif card.get("account_id") != account.get("account_id"):
        top_errors.append("card is not linked to the supplied account.")
    if as_of is None:
        return {"ok": False, "errors": top_errors, "warnings": top_warnings, "disputes": []}
    results = [validate_one(d if isinstance(d, dict) else {}, account, card, as_of, i)
               for i, d in enumerate(disputes)]
    return {"ok": not top_errors and all(r["ok"] for r in results), "errors": top_errors,
            "warnings": top_warnings, "disputes": results}


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(incoming), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": [], "disputes": []}))
