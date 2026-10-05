#!/usr/bin/env python3
"""Validate and plan debit-card dispute filings.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the input schema. This helper performs no bank action and intentionally rejects
unknown facts rather than filling them from assumptions.
"""
import json
import sys
from datetime import datetime, date

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
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ELIGIBLE = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
ONGOING = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def text_match(description, query):
    """Conservative normalized substring matching for a user-supplied merchant name."""
    if not isinstance(description, str) or not isinstance(query, str):
        return False
    normalize = lambda s: "".join(ch.lower() for ch in s if ch.isalnum())
    q = normalize(query)
    return bool(q) and q in normalize(description)


def amount_equal(left, right):
    try:
        return abs(abs(float(left)) - abs(float(right))) < 0.005
    except (TypeError, ValueError):
        return False


def ongoing_count(disputes, account_id):
    return sum(1 for d in disputes if d.get("account_id") == account_id and d.get("status") in ONGOING)


def choose_transaction(case, transactions, account_id):
    """Return (transaction, error). Duplicate selection is earliest dated matching debit."""
    target_date = case.get("transaction_date")
    target_amount = case.get("disputed_amount")
    candidates = [
        t for t in transactions
        if t.get("account_id") == account_id
        and t.get("status") == "posted"
        and isinstance(t.get("transaction_id"), str)
        and t.get("date") == target_date
        and amount_equal(t.get("amount"), target_amount)
        and float(t.get("amount", 0)) < 0
        and text_match(t.get("description", ""), case.get("merchant_query", ""))
    ]
    if not candidates:
        return None, "No matching posted debit transaction was found; retrieve and reconcile transaction history."
    if case.get("dispute_category") != "duplicate_charge":
        if len(candidates) != 1:
            return None, "More than one transaction matches; identify the exact transaction_id before filing."
        return candidates[0], None
    # The source records only dates, not timestamps. A unique earliest date is safe;
    # ties on that earliest date must be resolved outside this helper.
    dated = [(parse_date(t.get("date")), t) for t in candidates]
    if any(d is None for d, _ in dated):
        return None, "Matching transaction has an invalid date."
    earliest = min(d for d, _ in dated)
    earliest_rows = [t for d, t in dated if d == earliest]
    if len(earliest_rows) != 1:
        return None, "Duplicate candidates tie for earliest date; obtain transaction ordering before filing."
    return earliest_rows[0], None


def provisional(case, account, transaction_amount, as_of):
    reasons = []
    category = case.get("dispute_category")
    timely = case.get("timely_statement_reporting")
    if timely is not True:
        reasons.append("Timely reporting within 60 days of the statement is not established.")
    if category not in ELIGIBLE:
        reasons.append("This category does not require provisional credit.")
    if case.get("written_statement_provided") is not True:
        reasons.append("Written statement is not provided.")
    if str(account.get("status", "")).upper() != "OPEN" or account.get("has_hold_or_restriction") is not False:
        reasons.append("Account is not confirmed OPEN and unrestricted.")
    if category not in FRAUD and case.get("contacted_merchant") is not True:
        reasons.append("Non-fraud merchant-contact requirement is not met.")
    if case.get("pin_compromised") == "yes_shared":
        reasons.append("PIN was voluntarily shared.")
    opened = parse_date(account.get("date_opened"))
    new_account = opened is None or (as_of - opened).days < 30
    if category == "card_not_present_fraud" and new_account:
        reasons.append("Card-not-present dispute is on an account under 30 days old (or age is unknown).")
    required = not reasons
    offset = case.get("liability_offset")
    credit_amount = None
    if required:
        if offset not in (0, 50, 500):
            reasons.append("Liability offset must be established as 0, 50, or 500 before calculating credit.")
            required = False
        else:
            credit_amount = round(max(0.0, abs(float(transaction_amount)) - float(offset)), 2)
    deadline = 20 if new_account else 10
    extended = new_account or case.get("international_or_outside_us_pos") is True
    return {
        "required": required,
        "reasons": reasons,
        "provisional_credit_amount": credit_amount,
        "credit_deadline_business_days": deadline,
        "investigation_deadline_business_days": 90 if extended else 45,
    }


def plan(data):
    blocking, warnings, filings = [], [], []
    account = data.get("account") or {}
    card = data.get("card") or {}
    user_id = data.get("user_id")
    as_of = parse_date(data.get("as_of_date"))
    if not as_of:
        return {"ready": False, "blocking": ["as_of_date must be MM/DD/YYYY."], "warnings": [], "filings": []}
    account_id = account.get("account_id")
    if not account_id or not user_id:
        blocking.append("account.account_id and user_id are required.")
    if str(account.get("account_type", "")).lower() != "checking":
        blocking.append("The selected account is not confirmed as a checking account.")
    if str(account.get("status", "")).upper() != "OPEN":
        blocking.append("Checking account must be OPEN.")
    if account.get("has_hold_or_restriction") is not False:
        blocking.append("Account holds/restrictions must be checked and absent.")
    if card.get("account_id") != account_id or card.get("user_id") != user_id or not card.get("card_id"):
        blocking.append("Card is not confirmed as linked to the selected account and user.")
    tier = str(account.get("account_class", "")).lower().replace(" tier", "")
    if tier not in LIMITS:
        blocking.append("Account tier must be Entry, Mid, Premium, or Elite.")
    else:
        current = ongoing_count(data.get("open_disputes") or [], account_id)
        if current + len(data.get("cases") or []) > LIMITS[tier]:
            blocking.append("Filing these cases would exceed the account's open-dispute limit.")
    for index, case in enumerate(data.get("cases") or [], 1):
        prefix = "Case %d: " % index
        local = []
        category = case.get("dispute_category")
        if category not in CATEGORIES:
            local.append("Invalid dispute category.")
        if case.get("transaction_type") not in TRANSACTION_TYPES:
            local.append("Invalid or missing transaction type.")
        if case.get("pin_compromised") not in PIN_VALUES:
            local.append("PIN-compromise value is required.")
        if not isinstance(case.get("card_in_possession"), bool):
            local.append("Card-possession answer is required.")
        if not isinstance(case.get("police_report_filed"), bool):
            local.append("Police-report answer is required.")
        if not isinstance(case.get("written_statement_provided"), bool):
            local.append("Written-statement answer is required.")
        if category not in FRAUD and case.get("contacted_merchant") is not True:
            local.append("Customer must attempt merchant resolution for this non-fraud dispute before filing.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and case.get("atm_network") not in {"rho_bank", "third_party"}:
            local.append("ATM ownership (Rho-Bank or third-party) is required.")
        if parse_date(case.get("transaction_date")) is None or parse_date(case.get("discovery_date")) is None:
            local.append("Transaction and discovery dates must be MM/DD/YYYY.")
        try:
            claimed = float(case.get("disputed_amount"))
            if claimed < 1:
                local.append("Disputed amount must be at least $1.00.")
        except (TypeError, ValueError):
            local.append("Disputed amount is invalid.")
            claimed = 0
        tx, tx_error = choose_transaction(case, data.get("transactions") or [], account_id)
        if tx_error:
            local.append(tx_error)
        elif (as_of - parse_date(tx["date"])).days > 60:
            local.append("Transaction is more than 60 days old.")
        if category in FRAUD and claimed > 500 and case.get("police_report_filed") is False:
            warnings.append(prefix + "Recommend a police report because suspected fraud exceeds $500.")
        if local:
            blocking.extend(prefix + x for x in local)
            continue
        pc = provisional(case, account, tx["amount"], as_of)
        args = {
            "transaction_id": tx["transaction_id"], "account_id": account_id, "card_id": card["card_id"], "user_id": user_id,
            "dispute_category": category, "transaction_date": case["transaction_date"], "discovery_date": case["discovery_date"],
            "disputed_amount": round(abs(float(tx["amount"])), 2), "transaction_type": case["transaction_type"],
            "card_in_possession": case["card_in_possession"], "pin_compromised": case["pin_compromised"],
            "contacted_merchant": case["contacted_merchant"], "police_report_filed": case["police_report_filed"],
            "written_statement_provided": case["written_statement_provided"], "provisional_credit_eligible": pc["required"],
            "card_action": CARD_ACTIONS[category],
        }
        filings.append({"case_number": index, "matched_transaction": tx, "tool_arguments": args, "provisional_credit": pc})
    return {"ready": not blocking, "blocking": blocking, "warnings": warnings, "filings": filings}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(plan(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready": False, "blocking": ["Planner input error: %s" % exc], "warnings": [], "filings": []}))
