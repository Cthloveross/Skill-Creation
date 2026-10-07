#!/usr/bin/env python3
"""Validate a normalized debit-dispute plan; stdin JSON -> stdout JSON.
This utility is advisory only and does not access banking systems.
"""
import json
import sys
from datetime import datetime, date

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
TIERS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
REQUIRED_CREDIT_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}

def parse(value, fmt):
    try:
        return datetime.strptime(value, fmt).date()
    except (TypeError, ValueError):
        return None

def business_days_between(start, end):
    """Count weekdays after start through end; holidays require bank records, not this helper."""
    if not start or not end or end < start:
        return None
    count, cursor = 0, start
    while cursor < end:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            count += 1
    return count

def num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def liability_band(statement_date, reported_date):
    days = business_days_between(statement_date, reported_date)
    if days is None:
        return {"known": False, "maximum_liability": None}
    if days <= 2:
        return {"known": True, "maximum_liability": 50, "band": "within_2_business_days"}
    if (reported_date - statement_date).days <= 60:
        return {"known": True, "maximum_liability": 500, "band": "within_60_days"}
    return {"known": True, "maximum_liability": None, "band": "after_60_days"}

def main(data):
    as_of = parse(data.get("as_of"), "%Y-%m-%d")
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    claims = data.get("claims") if isinstance(data.get("claims"), list) else []
    global_errors = []
    tier = account.get("tier")
    if not as_of:
        global_errors.append("as_of must be YYYY-MM-DD")
    if account.get("account_type") != "checking":
        global_errors.append("account must be a checking account")
    if account.get("status") != "OPEN":
        global_errors.append("account must be OPEN")
    if tier not in TIERS:
        global_errors.append("account tier must be ENTRY, MID, PREMIUM, or ELITE")
    count = account.get("open_dispute_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        global_errors.append("open_dispute_count must be a nonnegative integer from dispute status records")
    elif tier in TIERS and count >= TIERS[tier]:
        global_errors.append("account has reached its maximum open-dispute limit")

    # Find earliest dated entry in each supplied duplicate group.
    groups = {}
    for i, claim in enumerate(claims):
        if isinstance(claim, dict) and claim.get("duplicate_group"):
            dt = parse(claim.get("transaction_date"), "%m/%d/%Y")
            groups.setdefault(str(claim["duplicate_group"]), []).append((dt, i))
    earliest = {}
    for group, entries in groups.items():
        valid = [x for x in entries if x[0] is not None]
        if valid:
            earliest[group] = min(valid, key=lambda x: x[0])[1]

    plans = []
    for i, c in enumerate(claims):
        c = c if isinstance(c, dict) else {}
        errors = []
        tx_date = parse(c.get("transaction_date"), "%m/%d/%Y")
        statement_date = parse(c.get("statement_date"), "%m/%d/%Y")
        discovery_date = parse(c.get("discovery_date"), "%m/%d/%Y")
        reported_date = parse(c.get("reported_date"), "%m/%d/%Y")
        category = c.get("category")
        tx_amount, disputed = c.get("transaction_amount"), c.get("disputed_amount")
        if not c.get("transaction_id"):
            errors.append("transaction_id must come from a retrieved transaction")
        if not tx_date:
            errors.append("transaction_date must be MM/DD/YYYY")
        elif as_of and (tx_date > as_of or (as_of - tx_date).days > 60):
            errors.append("transaction must be within 60 days and not future dated")
        if not discovery_date:
            errors.append("discovery_date must be MM/DD/YYYY")
        if not reported_date:
            errors.append("reported_date must be MM/DD/YYYY")
        if category not in CATEGORIES:
            errors.append("invalid dispute category")
        if c.get("transaction_type") not in TYPES:
            errors.append("invalid transaction type")
        if c.get("pin_compromised") not in PINS:
            errors.append("invalid pin_compromised value")
        if not isinstance(c.get("card_in_possession"), bool):
            errors.append("card_in_possession must be boolean")
        if not num(tx_amount) or abs(tx_amount) < 1:
            errors.append("transaction_amount must represent a debit of at least $1")
        if not num(disputed) or disputed < 1:
            errors.append("disputed_amount must be at least $1")
        elif num(tx_amount) and disputed > abs(tx_amount):
            errors.append("disputed_amount cannot exceed transaction amount")
        if category and category not in {"card_present_fraud", "card_not_present_fraud"} and not c.get("contacted_merchant"):
            errors.append("merchant contact is required before this non-fraud filing")
        group = c.get("duplicate_group")
        if group and earliest.get(str(group)) is not None and earliest[str(group)] != i:
            errors.append("only the earliest transaction in a duplicate group may be filed")

        liability = liability_band(statement_date, reported_date)
        if not liability["known"]:
            errors.append("statement_date and reported_date are required to determine liability and timely reporting")
        account_new = False
        opened = parse(account.get("opened"), "%Y-%m-%d")
        if opened and as_of:
            account_new = (as_of - opened).days < 30
        required_credit = (
            liability.get("band") in {"within_2_business_days", "within_60_days"}
            and category in REQUIRED_CREDIT_CATEGORIES
            and c.get("written_statement_provided") is True
            and account.get("status") == "OPEN"
            and account.get("has_hold_or_restriction") is False
            and c.get("pin_compromised") != "yes_shared"
            and not (account_new and category == "card_not_present_fraud")
            and not (category not in {"card_present_fraud", "card_not_present_fraud"} and not c.get("contacted_merchant"))
        )
        plans.append({
            "index": i,
            "transaction_id": c.get("transaction_id"),
            "filing_ready": not (global_errors or errors),
            "errors": errors,
            "card_action": ACTIONS.get(category, "keep_active"),
            "provisional_credit_required": required_credit,
            "liability": liability,
            "atm_affidavit_notice_required": category == "atm_cash_discrepancy" and num(disputed) and disputed > 200,
        })
    return {"global_errors": global_errors, "claims": plans}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
