#!/usr/bin/env python3
"""Validate proposed debit-card disputes and build filing-tool payloads.

Input is one JSON object on stdin. Output is one JSON object on stdout. The
script is deterministic and has no network access or banking side effects.
It never substitutes account, card, transaction, statement-timing, or customer
facts: the executor must obtain those from the authorized banking workflow.

Input schema (important fields):
{
  "as_of_date":"MM/DD/YYYY",
  "account":{"account_id":"...","status":"OPEN","tier":"Entry|Mid|Premium|Elite",
             "date_opened":"MM/DD/YYYY","has_hold_or_restriction":false,
             "open_dispute_count":0},
  "card":{"card_id":"...","account_id":"...","user_id":"..."},
  "disputes":[{
    "transaction_id":"...", "transaction_date":"MM/DD/YYYY",
    "discovery_date":"MM/DD/YYYY", "amount":12.34, "category":"...",
    "transaction_type":"...", "card_in_possession":true,
    "pin_compromised":"no|yes_shared|yes_observed|unknown",
    "contacted_merchant":true, "police_report_filed":false,
    "written_statement_provided":true,
    "timely_reported_within_60_days_of_statement":true,
    "liability_timing":"within_2_business_days|within_60_days|after_60_days",
    "liability_offset":0
  }]
}
The result has ok/errors/warnings and one proposed_filing_payload per dispute.
"""
import json
import sys
from datetime import datetime

FMT = "%m/%d/%Y"
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
QUALIFYING = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTIONS = {
    "unauthorized_transaction": "freeze_pending_investigation",
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
}
LIABILITY_LIMITS = {
    "within_2_business_days": 50.0,
    "within_60_days": 500.0,
    "after_60_days": -1.0,
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, FMT).date()
    except ValueError:
        errors.append(f"{field} must be a valid MM/DD/YYYY date.")
        return None


def bool_field(value, field, errors):
    if not isinstance(value, bool):
        errors.append(f"{field} must be boolean.")
        return False
    return value


def tier_key(value):
    return str(value or "").lower().replace(" tier", "").strip()


def action_for(category):
    return ACTIONS.get(category, "keep_active")


def liability(dispute, amount, errors):
    timing = dispute.get("liability_timing")
    if timing not in LIABILITY_LIMITS:
        errors.append("liability_timing must be within_2_business_days, within_60_days, or after_60_days.")
        return None
    limit = LIABILITY_LIMITS[timing]
    return -1.0 if limit == -1.0 else round(min(float(amount), limit), 2)


def provisional(dispute, account, as_of, errors):
    category = dispute.get("category")
    timely = dispute.get("timely_reported_within_60_days_of_statement")
    written = dispute.get("written_statement_provided")
    merchant = dispute.get("contacted_merchant")
    pin = dispute.get("pin_compromised")
    if not isinstance(timely, bool):
        errors.append("timely_reported_within_60_days_of_statement must be boolean.")
    opened = parse_date(account.get("date_opened"), "account.date_opened", errors)
    new_account = bool(opened and (as_of - opened).days < 30)
    reasons = []
    if timely is not True:
        reasons.append("timely reporting within 60 days of the statement is not established")
    if category not in QUALIFYING:
        reasons.append("category is not one for which provisional credit is required")
    if written is not True:
        reasons.append("written statement is not established")
    if account.get("status") != "OPEN" or account.get("has_hold_or_restriction") is not False:
        reasons.append("account is not OPEN without holds/restrictions")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and merchant is not True:
        reasons.append("merchant contact is not established for this non-fraud dispute")
    if pin == "yes_shared":
        reasons.append("PIN was voluntarily shared")
    if new_account and category == "card_not_present_fraud":
        reasons.append("new account card-not-present claim")
    eligible = not reasons
    amount = dispute.get("amount", 0)
    offset = dispute.get("liability_offset", 0)
    if not isinstance(offset, (int, float)) or isinstance(offset, bool) or offset < 0:
        errors.append("liability_offset must be a nonnegative number.")
        offset = 0
    credit = max(0.0, round(float(amount) - float(offset), 2)) if eligible else None
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
        amount = 0.0
    category = dispute.get("category")
    if category not in CATEGORIES:
        errors.append("category is not an allowed dispute category.")
    ttype = dispute.get("transaction_type")
    if ttype not in TRANSACTION_TYPES:
        errors.append("transaction_type is not allowed.")
    if dispute.get("pin_compromised") not in PIN_VALUES:
        errors.append("pin_compromised is not allowed.")
    for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        bool_field(dispute.get(field), field, errors)
    if not isinstance(dispute.get("transaction_id"), str) or not dispute["transaction_id"].strip():
        errors.append("transaction_id is required.")
    max_liability = liability(dispute, amount, errors)
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
            "customer_max_liability_amount": max_liability,
            "card_action": action_for(category),
        }
    return {"index": index, "ok": not errors, "errors": errors, "warnings": warnings,
            "provisional_credit": pc, "proposed_filing_payload": payload}


def main(data):
    errors, warnings = [], []
    as_of = parse_date(data.get("as_of_date"), "as_of_date", errors)
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        errors.append("disputes must be a nonempty array.")
        disputes = []
    if account.get("status") != "OPEN":
        errors.append("account must have OPEN status.")
    if account.get("has_hold_or_restriction") is not False:
        errors.append("account must explicitly have no holds or restrictions.")
    if not all(isinstance(account.get(k), str) and account[k] for k in ("account_id", "tier", "date_opened")):
        errors.append("account_id, tier, and date_opened are required.")
    tier = tier_key(account.get("tier"))
    if tier not in TIER_LIMITS:
        errors.append("account tier must be Entry, Mid, Premium, or Elite.")
    count = account.get("open_dispute_count")
    if not isinstance(count, int) or count < 0:
        errors.append("open_dispute_count must be a nonnegative integer.")
    elif tier in TIER_LIMITS and count + len(disputes) > TIER_LIMITS[tier]:
        errors.append("requested disputes exceed the account tier open-dispute limit.")
    if not all(isinstance(card.get(k), str) and card[k] for k in ("card_id", "account_id", "user_id")):
        errors.append("card_id, card.account_id, and card.user_id are required.")
    elif card.get("account_id") != account.get("account_id"):
        errors.append("card is not linked to the supplied account.")
    if as_of is None:
        return {"ok": False, "errors": errors, "warnings": warnings, "disputes": []}
    results = [validate_one(x if isinstance(x, dict) else {}, account, card, as_of, i)
               for i, x in enumerate(disputes)]
    return {"ok": not errors and all(r["ok"] for r in results), "errors": errors,
            "warnings": warnings, "disputes": results}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(data), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": [], "disputes": []}))
