#!/usr/bin/env python3
"""Plan validated debit-card dispute filings.

Input: one JSON object on stdin following the schema in SKILL.md.
Output: {ready, blocking, warnings, filings} JSON on stdout.
This script is deterministic and does not call banking tools or change any account.
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
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
ELIGIBLE = FRAUD | {"unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"}
ONGOING = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}


def d(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date() if isinstance(value, str) else None
    except ValueError:
        return None


def money_equal(a, b):
    try:
        return abs(abs(float(a)) - abs(float(b))) < 0.005
    except (TypeError, ValueError):
        return False


def matches(description, query):
    if not isinstance(description, str) or not isinstance(query, str):
        return False
    norm = lambda x: "".join(ch.lower() for ch in x if ch.isalnum())
    q = norm(query)
    return bool(q) and q in norm(description)


def choose(case, rows, account_id):
    """Find the exact debit; duplicates require a uniquely determined earliest record."""
    candidates = []
    for row in rows:
        try:
            negative = float(row.get("amount")) < 0
        except (ValueError, TypeError):
            negative = False
        if (row.get("account_id") == account_id and row.get("status") == "posted"
                and isinstance(row.get("transaction_id"), str) and negative
                and row.get("date") == case.get("transaction_date")
                and money_equal(row.get("amount"), case.get("disputed_amount"))
                and matches(row.get("description"), case.get("merchant_query"))):
            candidates.append(row)
    if not candidates:
        return None, "No matching posted debit was found in retrieved transaction history."
    if case.get("dispute_category") != "duplicate_charge":
        return (candidates[0], None) if len(candidates) == 1 else (None, "More than one debit matches; identify the exact transaction ID.")
    parsed = [(d(r.get("date")), r) for r in candidates]
    if any(day is None for day, _ in parsed):
        return None, "A matching transaction has an invalid date."
    first = min(day for day, _ in parsed)
    earliest = [row for day, row in parsed if day == first]
    if len(earliest) != 1:
        return None, "Duplicate candidates tie for earliest date; obtain transaction ordering before filing."
    return earliest[0], None


def credit(case, account, amount, as_of):
    reasons = []
    category = case.get("dispute_category")
    if case.get("timely_statement_reporting") is not True:
        reasons.append("Timely reporting within 60 days of the statement is not established.")
    if category not in ELIGIBLE:
        reasons.append("Category does not require provisional credit.")
    if case.get("written_statement_provided") is not True:
        reasons.append("Written statement is not provided.")
    if str(account.get("status", "")).upper() != "OPEN" or account.get("has_hold_or_restriction") is not False:
        reasons.append("Account is not confirmed OPEN and unrestricted.")
    if category not in FRAUD and case.get("contacted_merchant") is not True:
        reasons.append("Required non-fraud merchant contact is not established.")
    if case.get("pin_compromised") == "yes_shared":
        reasons.append("PIN was voluntarily shared.")
    opened = d(account.get("date_opened"))
    new = opened is None or (as_of - opened).days < 30
    if category == "card_not_present_fraud" and new:
        reasons.append("Card-not-present fraud is on an account under 30 days old, or account age is unknown.")
    required = not reasons
    offset = case.get("liability_offset")
    value = None
    if required:
        if offset not in (0, 50, 500):
            required = False
            reasons.append("Liability offset must be established as 0, 50, or 500.")
        else:
            value = round(max(0, abs(float(amount)) - float(offset)), 2)
    return {"required": required, "reasons": reasons, "provisional_credit_amount": value,
            "credit_deadline_business_days": 20 if new else 10,
            "investigation_deadline_business_days": 90 if new or case.get("international_or_outside_us_pos") is True else 45}


def plan(data):
    blocking, warnings, filings = [], [], []
    account, card = data.get("account") or {}, data.get("card") or {}
    account_id, user_id, as_of = account.get("account_id"), data.get("user_id"), d(data.get("as_of_date"))
    if not as_of:
        return {"ready": False, "blocking": ["as_of_date must be MM/DD/YYYY."], "warnings": [], "filings": []}
    if not account_id or not user_id:
        blocking.append("account.account_id and user_id are required.")
    if str(account.get("account_type", "")).lower() != "checking":
        blocking.append("Selected account is not confirmed as checking.")
    if str(account.get("status", "")).upper() != "OPEN" or account.get("has_hold_or_restriction") is not False:
        blocking.append("Checking account must be OPEN with no holds or restrictions.")
    if card.get("account_id") != account_id or card.get("user_id") != user_id or not card.get("card_id"):
        blocking.append("Card is not confirmed as linked to selected account and verified user.")
    tier = str(account.get("account_class", "")).lower().replace(" tier", "")
    cases = data.get("cases") or []
    if tier not in LIMITS:
        blocking.append("Account tier must be Entry, Mid, Premium, or Elite.")
    else:
        active = sum(x.get("account_id") == account_id and x.get("status") in ONGOING for x in data.get("open_disputes") or [])
        if active + len(cases) > LIMITS[tier]:
            blocking.append("Proposed filings exceed the account open-dispute limit.")
    for number, case in enumerate(cases, 1):
        errors, prefix = [], "Case %d: " % number
        category = case.get("dispute_category")
        if category not in CATEGORIES: errors.append("Invalid dispute category.")
        if case.get("transaction_type") not in TYPES: errors.append("Invalid transaction type.")
        if case.get("pin_compromised") not in PINS: errors.append("PIN-compromise value is required.")
        for key, label in (("card_in_possession", "Card-possession"), ("contacted_merchant", "Merchant-contact"), ("police_report_filed", "Police-report"), ("written_statement_provided", "Written-statement")):
            if not isinstance(case.get(key), bool): errors.append(label + " response must be boolean.")
        if category not in FRAUD and case.get("contacted_merchant") is not True:
            errors.append("Customer must attempt merchant resolution before this non-fraud filing.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and case.get("atm_network") not in {"rho_bank", "third_party"}:
            errors.append("ATM ownership is required.")
        when, found = d(case.get("transaction_date")), d(case.get("discovery_date"))
        if not when or not found: errors.append("Transaction and discovery dates must be MM/DD/YYYY.")
        try:
            claimed = float(case.get("disputed_amount"))
            if claimed < 1: errors.append("Disputed amount must be at least $1.00.")
        except (ValueError, TypeError):
            claimed = 0
            errors.append("Disputed amount is invalid.")
        tx, problem = choose(case, data.get("transactions") or [], account_id)
        if problem: errors.append(problem)
        elif (as_of - d(tx["date"])).days > 60: errors.append("Transaction is more than 60 days old.")
        elif d(tx["date"]) > as_of: errors.append("Transaction date is after as_of_date.")
        if category in FRAUD and claimed > 500 and case.get("police_report_filed") is False:
            warnings.append(prefix + "Recommend a police report for suspected fraud over $500.")
        if errors:
            blocking.extend(prefix + item for item in errors)
            continue
        pc = credit(case, account, tx["amount"], as_of)
        args = {"transaction_id": tx["transaction_id"], "account_id": account_id, "card_id": card["card_id"], "user_id": user_id,
                "dispute_category": category, "transaction_date": case["transaction_date"], "discovery_date": case["discovery_date"],
                "disputed_amount": round(abs(float(tx["amount"])), 2), "transaction_type": case["transaction_type"],
                "card_in_possession": case["card_in_possession"], "pin_compromised": case["pin_compromised"],
                "contacted_merchant": case["contacted_merchant"], "police_report_filed": case["police_report_filed"],
                "written_statement_provided": case["written_statement_provided"], "provisional_credit_eligible": pc["required"],
                "card_action": ACTIONS[category]}
        filings.append({"case_number": number, "matched_transaction": tx, "tool_arguments": args, "provisional_credit": pc})
    return {"ready": not blocking, "blocking": blocking, "warnings": warnings, "filings": filings}


if __name__ == "__main__":
    try:
        print(json.dumps(plan(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready": False, "blocking": ["Planner input error: %s" % exc], "warnings": [], "filings": []}))
