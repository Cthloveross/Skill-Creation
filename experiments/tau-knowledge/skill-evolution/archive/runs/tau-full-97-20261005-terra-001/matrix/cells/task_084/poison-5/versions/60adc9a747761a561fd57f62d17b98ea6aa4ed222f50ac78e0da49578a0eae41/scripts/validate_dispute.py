#!/usr/bin/env python3
"""Validate one proposed debit-card dispute without performing bank actions.

Input is a JSON object with these fields:
  now, identity_verified, authority_confirmed, user_id, account, card,
  transactions, open_disputes, account_tier, statement_reported_within_60_days,
  candidate.

account must include account_id, account_type, status,
has_holds_or_restrictions, and date_opened. card must include card_id,
account_id, and user_id. Each transaction must include transaction_id,
account_id, date, amount, and status. For duplicate_charge, candidate must
include duplicate_transaction_ids_earliest_first, established from the
reverse-chronological history as earliest first.

Writes JSON with ready, missing_or_invalid, open_dispute_count,
open_dispute_limit, tool_payload, provisional_credit, and
post_filing_card_action.
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
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
UNRESOLVED = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}
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


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(label + " must be MM/DD/YYYY")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(label + " must be MM/DD/YYYY")
        return None


def is_bool(value):
    return isinstance(value, bool)


def main(data):
    errors = []
    required = (
        "now", "identity_verified", "authority_confirmed", "user_id", "account",
        "card", "transactions", "open_disputes", "account_tier",
        "statement_reported_within_60_days", "candidate",
    )
    for key in required:
        if key not in data:
            errors.append("missing top-level field: " + key)
    if errors:
        return {"ready": False, "missing_or_invalid": errors, "tool_payload": None}

    now = parse_date(data["now"], "now", errors)
    account = data["account"] if isinstance(data["account"], dict) else {}
    card = data["card"] if isinstance(data["card"], dict) else {}
    candidate = data["candidate"] if isinstance(data["candidate"], dict) else {}
    user_id = data["user_id"]

    if data["identity_verified"] is not True:
        errors.append("identity verification has not been completed and logged")
    if data["authority_confirmed"] is not True:
        errors.append("customer authority/account ownership is not confirmed")
    if not isinstance(user_id, str) or not user_id:
        errors.append("user_id must be a nonempty string")
    if account.get("account_type") != "checking":
        errors.append("selected account is not a checking account")
    if account.get("status") != "OPEN":
        errors.append("selected checking account is not OPEN")
    if not account.get("account_id"):
        errors.append("missing selected account_id")
    if not card.get("card_id"):
        errors.append("missing card_id")
    if card.get("account_id") != account.get("account_id"):
        errors.append("card is not linked to selected account")
    if card.get("user_id") != user_id:
        errors.append("card user_id does not match verified user")

    tier = data["account_tier"]
    if tier not in LIMITS:
        errors.append("account_tier must be Entry, Mid, Premium, or Elite")
    disputes = data["open_disputes"]
    if not isinstance(disputes, list):
        errors.append("open_disputes must be a list")
        disputes = []
    open_count = sum(
        1 for dispute in disputes
        if isinstance(dispute, dict)
        and dispute.get("account_id") == account.get("account_id")
        and dispute.get("status") in UNRESOLVED
    )
    if tier in LIMITS and open_count >= LIMITS[tier]:
        errors.append("open-dispute limit reached for selected account (%d/%d)" % (open_count, LIMITS[tier]))

    transactions = data["transactions"]
    if not isinstance(transactions, list):
        errors.append("transactions must be a list")
        transactions = []
    transaction_id = candidate.get("transaction_id")
    matching = [tx for tx in transactions if isinstance(tx, dict) and tx.get("transaction_id") == transaction_id]
    if len(matching) != 1:
        errors.append("candidate transaction_id must match exactly one retrieved transaction")
        transaction = {}
    else:
        transaction = matching[0]

    transaction_date = parse_date(transaction.get("date"), "transaction date", errors) if transaction else None
    discovery_date = parse_date(candidate.get("discovery_date"), "discovery_date", errors)
    if transaction and transaction.get("account_id") != account.get("account_id"):
        errors.append("transaction is not on selected account")
    if transaction and transaction.get("status") != "posted":
        errors.append("transaction is not posted")

    amount = transaction.get("amount") if transaction else None
    disputed_amount = None
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        errors.append("retrieved transaction amount must be numeric")
    else:
        disputed_amount = abs(float(amount))
        if amount >= 0:
            errors.append("retrieved transaction is not a debit")
        if disputed_amount < 1.0:
            errors.append("transaction amount is below $1.00")
    if transaction_date and now:
        age_days = (now - transaction_date).days
        if age_days < 0 or age_days > 60:
            errors.append("transaction is not within 60 calendar days of filing")
    if transaction_date and discovery_date and discovery_date < transaction_date:
        errors.append("discovery_date cannot precede transaction date")

    category = candidate.get("dispute_category")
    if category not in CATEGORIES:
        errors.append("invalid dispute_category")
    if candidate.get("transaction_type") not in TRANSACTION_TYPES:
        errors.append("invalid transaction_type")
    if candidate.get("pin_compromised") not in PIN_VALUES:
        errors.append("invalid pin_compromised value")
    for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not is_bool(candidate.get(key)):
            errors.append(key + " must be boolean")

    if category == "duplicate_charge":
        ordered_ids = candidate.get("duplicate_transaction_ids_earliest_first")
        if not isinstance(ordered_ids, list) or not ordered_ids:
            errors.append("duplicate charge requires duplicate_transaction_ids_earliest_first")
        elif ordered_ids[0] != transaction_id:
            errors.append("duplicate dispute must target the earliest transaction")

    timely = data["statement_reported_within_60_days"]
    if timely not in (True, False, None):
        errors.append("statement_reported_within_60_days must be true, false, or null")
    account_opened = parse_date(account.get("date_opened"), "account date_opened", errors)
    is_new_account = bool(now and account_opened and 0 <= (now - account_opened).days < 30)
    restricted = account.get("has_holds_or_restrictions")
    if not is_bool(restricted):
        errors.append("has_holds_or_restrictions must be boolean")

    merchant_not_contacted_nonfraud = candidate.get("contacted_merchant") is False and category not in FRAUD_CATEGORIES
    disqualifiers = []
    if category not in PC_CATEGORIES:
        disqualifiers.append("category is not provisionally-credit eligible")
    if merchant_not_contacted_nonfraud:
        disqualifiers.append("merchant was not contacted for non-fraud dispute")
    if candidate.get("pin_compromised") == "yes_shared":
        disqualifiers.append("PIN was voluntarily shared")
    if is_new_account and category == "card_not_present_fraud":
        disqualifiers.append("new-account card-not-present exclusion")
    if restricted is True:
        disqualifiers.append("account has holds or restrictions")
    if timely is False:
        disqualifiers.append("reporting was not within 60 days of statement")

    provisional_eligible = (
        not disqualifiers
        and timely is True
        and candidate.get("written_statement_provided") is True
        and account.get("status") == "OPEN"
    )
    pc_reasons = list(disqualifiers)
    if not disqualifiers and timely is None:
        pc_reasons.append("statement reporting timeliness is unknown")
    if not disqualifiers and candidate.get("written_statement_provided") is not True:
        pc_reasons.append("written statement is not provided")

    payload = None
    if not errors:
        payload = {
            "transaction_id": transaction_id,
            "account_id": account["account_id"],
            "card_id": card["card_id"],
            "user_id": user_id,
            "dispute_category": category,
            "transaction_date": transaction["date"],
            "discovery_date": candidate["discovery_date"],
            "disputed_amount": disputed_amount,
            "transaction_type": candidate["transaction_type"],
            "card_in_possession": candidate["card_in_possession"],
            "pin_compromised": candidate["pin_compromised"],
            "contacted_merchant": candidate["contacted_merchant"],
            "police_report_filed": candidate["police_report_filed"],
            "written_statement_provided": candidate["written_statement_provided"],
            "provisional_credit_eligible": provisional_eligible,
            "card_action": ACTIONS.get(category),
        }

    return {
        "ready": not errors,
        "missing_or_invalid": errors,
        "open_dispute_count": open_count,
        "open_dispute_limit": LIMITS.get(tier),
        "tool_payload": payload,
        "provisional_credit": {
            "eligible": provisional_eligible,
            "reasons": pc_reasons,
            "timeline_business_days": 20 if is_new_account else 10,
            "amount_before_any_late_liability_offset": disputed_amount if provisional_eligible else 0.0,
        },
        "post_filing_card_action": ACTIONS.get(category),
    }


try:
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict):
        raise ValueError("top-level JSON must be an object")
    print(json.dumps(main(raw), sort_keys=True))
except Exception as exc:
    print(json.dumps({
        "ready": False,
        "missing_or_invalid": ["invalid input: " + str(exc)],
        "tool_payload": None,
    }))
