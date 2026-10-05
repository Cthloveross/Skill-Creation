#!/usr/bin/env python3
"""Validate one proposed debit-card dispute without performing bank actions.

stdin JSON schema:
{
  "now": "MM/DD/YYYY", "identity_verified": bool,
  "authority_confirmed": bool, "user_id": str,
  "account": {"account_id": str, "account_type": "checking", "status": "OPEN",
              "has_holds_or_restrictions": bool, "date_opened": "MM/DD/YYYY"},
  "card": {"card_id": str, "account_id": str, "user_id": str},
  "transactions": [{"transaction_id": str, "account_id": str, "date": "MM/DD/YYYY",
                    "description": str, "amount": number, "status": "posted"}],
  "open_disputes": [{"account_id": str, "status": str}],
  "account_tier": "Entry|Mid|Premium|Elite",
  "statement_reported_within_60_days": true|false|null,
  "candidate": {"transaction_id": str, "dispute_category": str,
     "discovery_date": "MM/DD/YYYY", "transaction_type": str,
     "card_in_possession": bool, "pin_compromised": str,
     "contacted_merchant": bool, "police_report_filed": bool,
     "written_statement_provided": bool,
     "duplicate_transaction_ids_earliest_first": [str]}
}

The duplicate list is required only for duplicate_charge and is supplied in known
chronological order, earliest first. stdout is one JSON object.
"""
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
LIMITS = {"Entry": 2, "Mid": 3, "Premium": 4, "Elite": 5}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
                 "atm_cash_discrepancy", "duplicate_charge"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}

def date_value(value, label, errors):
    if not isinstance(value, str):
        errors.append(label + " must be MM/DD/YYYY")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(label + " must be MM/DD/YYYY")
        return None

def main(data):
    errors = []
    for key in ("now", "identity_verified", "authority_confirmed", "user_id", "account", "card",
                "transactions", "open_disputes", "account_tier", "candidate"):
        if key not in data:
            errors.append("missing top-level field: " + key)
    if errors:
        return {"ready": False, "missing_or_invalid": errors, "tool_payload": None}

    now = date_value(data["now"], "now", errors)
    account = data["account"] if isinstance(data["account"], dict) else {}
    card = data["card"] if isinstance(data["card"], dict) else {}
    candidate = data["candidate"] if isinstance(data["candidate"], dict) else {}
    uid = data["user_id"]

    if data["identity_verified"] is not True:
        errors.append("identity verification has not been completed and logged")
    if data["authority_confirmed"] is not True:
        errors.append("customer authority/account ownership is not confirmed")
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
    if card.get("user_id") != uid:
        errors.append("card user_id does not match verified user")

    tier = data["account_tier"]
    if tier not in LIMITS:
        errors.append("account_tier must be Entry, Mid, Premium, or Elite")
    disputes = data["open_disputes"]
    if not isinstance(disputes, list):
        errors.append("open_disputes must be a list")
        disputes = []
    open_count = sum(1 for d in disputes if isinstance(d, dict)
                     and d.get("account_id") == account.get("account_id")
                     and d.get("status") in OPEN_STATUSES)
    if tier in LIMITS and open_count >= LIMITS[tier]:
        errors.append("open-dispute limit reached for selected account (%d/%d)" % (open_count, LIMITS[tier]))

    txid = candidate.get("transaction_id")
    matches = [t for t in data["transactions"] if isinstance(t, dict) and t.get("transaction_id") == txid]
    if len(matches) != 1:
        errors.append("candidate transaction_id must match exactly one retrieved transaction")
        tx = {}
    else:
        tx = matches[0]
    tx_date = date_value(tx.get("date"), "transaction date", errors) if tx else None
    discovery = date_value(candidate.get("discovery_date"), "discovery_date", errors)
    if tx and tx.get("account_id") != account.get("account_id"):
        errors.append("transaction is not on selected account")
    if tx and tx.get("status") != "posted":
        errors.append("transaction is not posted")
    amount = tx.get("amount") if tx else None
    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        errors.append("retrieved transaction amount must be numeric")
        disputed_amount = None
    else:
        disputed_amount = abs(float(amount))
        if amount >= 0:
            errors.append("retrieved transaction is not a debit")
        if disputed_amount < 1.0:
            errors.append("transaction amount is below $1.00")
    if tx_date and now:
        age = (now - tx_date).days
        if age < 0 or age > 60:
            errors.append("transaction is not within 60 calendar days of filing")
    if discovery and tx_date and discovery < tx_date:
        errors.append("discovery_date cannot precede transaction date")

    category = candidate.get("dispute_category")
    if category not in CATEGORIES:
        errors.append("invalid dispute_category")
    if candidate.get("transaction_type") not in TYPES:
        errors.append("invalid transaction_type")
    if candidate.get("pin_compromised") not in PINS:
        errors.append("invalid pin_compromised value")
    for key in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not isinstance(candidate.get(key), bool):
            errors.append(key + " must be boolean")
    if category == "duplicate_charge":
        ordered = candidate.get("duplicate_transaction_ids_earliest_first")
        if not isinstance(ordered, list) or not ordered:
            errors.append("duplicate charge requires duplicate_transaction_ids_earliest_first")
        elif ordered[0] != txid:
            errors.append("duplicate dispute must target the earliest transaction")

    statement_timely = data.get("statement_reported_within_60_days")
    if statement_timely not in (True, False, None):
        errors.append("statement_reported_within_60_days must be true, false, or null")
    opened = date_value(account.get("date_opened"), "account date_opened", errors)
    is_new = bool(now and opened and 0 <= (now - opened).days < 30)
    has_restrictions = account.get("has_holds_or_restrictions")
    if not isinstance(has_restrictions, bool):
        errors.append("has_holds_or_restrictions must be boolean")

    known_disqualifier = (
        category not in PC_CATEGORIES or
        candidate.get("contacted_merchant") is False and category not in {"card_present_fraud", "card_not_present_fraud"} or
        candidate.get("pin_compromised") == "yes_shared" or
        (is_new and category == "card_not_present_fraud") or
        has_restrictions is True
    )
    pc_eligible = (not known_disqualifier and statement_timely is True and
                   candidate.get("written_statement_provided") is True and
                   account.get("status") == "OPEN")
    pc_reasons = []
    if category not in PC_CATEGORIES: pc_reasons.append("category is not provisionally-credit eligible")
    if candidate.get("contacted_merchant") is False and category not in {"card_present_fraud", "card_not_present_fraud"}: pc_reasons.append("merchant was not contacted for non-fraud dispute")
    if candidate.get("pin_compromised") == "yes_shared": pc_reasons.append("PIN was voluntarily shared")
    if is_new and category == "card_not_present_fraud": pc_reasons.append("new account card-not-present exclusion")
    if has_restrictions is True: pc_reasons.append("account has holds or restrictions")
    if statement_timely is False: pc_reasons.append("reporting was not within 60 days of statement")
    if statement_timely is None and not known_disqualifier: pc_reasons.append("statement reporting timeliness is unknown")
    if candidate.get("written_statement_provided") is not True and not known_disqualifier: pc_reasons.append("written statement is not provided")

    payload = None
    if not errors:
        payload = {
            "transaction_id": txid, "account_id": account["account_id"], "card_id": card["card_id"],
            "user_id": uid, "dispute_category": category, "transaction_date": tx["date"],
            "discovery_date": candidate["discovery_date"], "disputed_amount": disputed_amount,
            "transaction_type": candidate["transaction_type"], "card_in_possession": candidate["card_in_possession"],
            "pin_compromised": candidate["pin_compromised"], "contacted_merchant": candidate["contacted_merchant"],
            "police_report_filed": candidate["police_report_filed"],
            "written_statement_provided": candidate["written_statement_provided"],
            "provisional_credit_eligible": pc_eligible, "card_action": ACTIONS.get(category)
        }
    return {"ready": not errors, "missing_or_invalid": errors, "open_dispute_count": open_count,
            "open_dispute_limit": LIMITS.get(tier), "tool_payload": payload,
            "provisional_credit": {"eligible": pc_eligible, "reasons": pc_reasons,
                                   "timeline_business_days": 20 if is_new else 10,
                                   "amount_before_any_late_liability_offset": disputed_amount if pc_eligible else 0.0},
            "post_filing_card_action": ACTIONS.get(category)}

try:
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict):
        raise ValueError("top-level JSON must be an object")
    print(json.dumps(main(raw), sort_keys=True))
except Exception as exc:
    print(json.dumps({"ready": False, "missing_or_invalid": ["invalid input: " + str(exc)], "tool_payload": None}))
