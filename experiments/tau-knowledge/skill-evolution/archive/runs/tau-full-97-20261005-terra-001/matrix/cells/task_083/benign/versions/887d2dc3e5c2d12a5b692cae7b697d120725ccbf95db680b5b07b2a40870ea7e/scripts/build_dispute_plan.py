#!/usr/bin/env python3
"""Validate debit-card dispute facts and construct safe filing proposals.

Reads one JSON object from stdin and writes one JSON object to stdout. This program
never invokes banking tools and does not mutate external state.
"""
import json
import sys
from datetime import date, datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
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
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
ACTIVE_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
MERCHANT_CONTACT_CATEGORIES = {
    "unauthorized_transaction", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def mmddyyyy(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else None


def canonical_tier(account):
    raw = str(account.get("tier") or account.get("account_class") or "").strip().lower()
    if raw in LIMITS:
        return raw
    # Account class labels documented for personal checking products.
    if raw in {"light blue account", "light green account", "green fee-free account"}:
        return "entry"
    if raw in {"blue account", "green account", "green account (checking)"}:
        return "mid"
    if raw == "evergreen account":
        return "premium"
    if raw == "bluest account":
        return "elite"
    return None


def category_for(case):
    supplied = case.get("dispute_category")
    if supplied:
        return supplied
    issue = case.get("issue_kind")
    if issue == "unauthorized":
        if case.get("fraud_suspected") is True:
            return "card_present_fraud" if case.get("card_present") is True else "card_not_present_fraud"
        if case.get("fraud_suspected") is False:
            return "unauthorized_transaction"
    mapping = {
        "atm_cash_discrepancy": "atm_cash_discrepancy",
        "atm_deposit_not_credited": "atm_deposit_not_credited",
        "duplicate": "duplicate_charge",
        "incorrect_amount": "incorrect_amount",
        "goods_services_not_received": "goods_services_not_received",
        "recurring_charge_after_cancellation": "recurring_charge_after_cancellation",
    }
    return mapping.get(issue)


def account_is_checking(account):
    return str(account.get("account_type", "")).strip().lower() == "checking"


def output_error(message):
    print(json.dumps({"ready_filings": [], "blocked_cases": [], "notices": [], "card_actions": [], "global_blockers": [message]}, indent=2))


def main(state):
    today = parse_date(state.get("current_date"))
    if not today:
        output_error("current_date is required in YYYY-MM-DD or MM/DD/YYYY format")
        return

    global_blockers = []
    if state.get("customer_verified") is not True:
        global_blockers.append("Customer identity has not been verified and logged.")
    if not state.get("user_id"):
        global_blockers.append("A verified user_id is required.")

    accounts = {a.get("account_id"): a for a in state.get("accounts", []) if a.get("account_id")}
    cards = {c.get("card_id"): c for c in state.get("cards", []) if c.get("card_id")}
    active_counts = {}
    for dispute in state.get("open_disputes", []):
        if str(dispute.get("status", "")).upper() in ACTIVE_STATUSES and dispute.get("account_id"):
            aid = dispute["account_id"]
            active_counts[aid] = active_counts.get(aid, 0) + 1

    ready, blocked, notices = [], [], []
    scheduled_by_account = {}
    card_actions = {}

    for case in state.get("cases", []):
        cid = case.get("case_id", "unidentified_case")
        blockers = list(global_blockers)
        case_notices = []
        category = category_for(case)
        account = accounts.get(case.get("account_id"))
        card = cards.get(case.get("card_id"))
        txn = case.get("transaction") if isinstance(case.get("transaction"), dict) else {}

        if category not in CATEGORIES:
            blockers.append("A supported dispute_category, or sufficient issue_kind/fraud facts to derive one, is required.")
        if not account:
            blockers.append("The linked account was not retrieved.")
        else:
            if not account_is_checking(account):
                blockers.append("The linked account is not a checking account.")
            if str(account.get("status", "")).upper() != "OPEN":
                blockers.append("The linked checking account is not OPEN.")
        if not card:
            blockers.append("The debit card was not retrieved.")
        else:
            if card.get("account_id") != case.get("account_id"):
                blockers.append("The card is not linked to the specified checking account.")
            if state.get("user_id") and card.get("user_id") != state.get("user_id"):
                blockers.append("The cardholder does not match the verified customer.")
        if not txn.get("transaction_id"):
            blockers.append("A matched transaction_id is required.")
        transaction_date = parse_date(txn.get("date"))
        if not transaction_date:
            blockers.append("Matched transaction date is missing or invalid.")
        else:
            age = (today - transaction_date).days
            if age < 0:
                blockers.append("Transaction date cannot be in the future.")
            elif age > 60:
                blockers.append("Transaction is more than 60 days old.")
        if case.get("transaction_type") not in TRANSACTION_TYPES:
            blockers.append("A supported transaction_type is required.")
        discovery = mmddyyyy(case.get("discovery_date"))
        if not discovery:
            blockers.append("A valid discovery_date is required.")
        if case.get("card_in_possession") not in (True, False):
            blockers.append("card_in_possession must be explicitly true or false.")
        if case.get("pin_compromised") not in PINS:
            blockers.append("pin_compromised must be yes_shared, yes_observed, no, or unknown.")
        if case.get("written_statement_provided") not in (True, False):
            blockers.append("written_statement_provided must be explicitly true or false.")

        amount = case.get("disputed_amount")
        if amount is None and category == "atm_cash_discrepancy":
            requested, received = case.get("requested_amount"), case.get("cash_received")
            if isinstance(requested, (int, float)) and isinstance(received, (int, float)):
                amount = requested - received
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
            blockers.append("disputed_amount must be a numeric amount of at least $1.00.")
        else:
            debit = txn.get("amount")
            if not isinstance(debit, (int, float)) or isinstance(debit, bool) or debit >= 0:
                blockers.append("Matched transaction must be a debit with a negative numeric amount.")
            elif amount > abs(debit) + 1e-9:
                blockers.append("disputed_amount cannot exceed the matched debit transaction amount.")

        if category in MERCHANT_CONTACT_CATEGORIES:
            if case.get("contacted_merchant") is not True:
                blockers.append("Merchant contact is required for this non-fraud merchant dispute before filing.")
        elif "contacted_merchant" not in case:
            blockers.append("contacted_merchant must be recorded as true or false (false is valid when not applicable).")

        if category == "duplicate_charge":
            candidates = case.get("duplicate_candidates")
            if not isinstance(candidates, list) or not candidates:
                blockers.append("Duplicate candidates are required to verify that the earliest duplicate is filed first.")
            else:
                dated = [(parse_date(x.get("date")), x.get("transaction_id")) for x in candidates if isinstance(x, dict)]
                dated = [(d, tid) for d, tid in dated if d and tid]
                if not dated:
                    blockers.append("Duplicate candidates need valid dates and transaction IDs.")
                else:
                    earliest = min(dated, key=lambda item: item[0])[1]
                    if txn.get("transaction_id") != earliest:
                        blockers.append("File the earliest duplicate transaction first.")

        tier = canonical_tier(account) if account else None
        if account and not tier:
            blockers.append("Account tier/class cannot be mapped to a dispute limit.")
        if tier:
            projected = active_counts.get(case.get("account_id"), 0) + scheduled_by_account.get(case.get("account_id"), 0) + 1
            if projected > LIMITS[tier]:
                blockers.append("Filing would exceed the account's maximum active-dispute limit.")

        is_fraud = category in {"card_present_fraud", "card_not_present_fraud"}
        if is_fraud and isinstance(amount, (int, float)) and amount > 500:
            if "police_report_filed" not in case or case.get("police_report_filed") not in (True, False):
                blockers.append("police_report_filed must be collected for fraud disputes over $500.")
            elif case.get("police_report_filed") is False:
                case_notices.append("Recommend that the customer file a police report for the fraud dispute over $500.")
        police = case.get("police_report_filed", False)
        if police not in (True, False):
            police = False

        # Regulation E provisional-credit determination is intentionally conservative:
        # an unknown statement-date fact cannot establish mandatory eligibility.
        pc_reasons = []
        if category not in PC_CATEGORIES:
            pc_reasons.append("category is not one that requires provisional credit")
        if case.get("reported_within_60_days_of_statement") is not True:
            pc_reasons.append("timely reporting within 60 days of the statement is not established")
        if case.get("written_statement_provided") is not True:
            pc_reasons.append("written statement is not provided")
        if not account or str(account.get("status", "")).upper() != "OPEN" or account.get("has_holds_or_restrictions") is True:
            pc_reasons.append("account is not confirmed OPEN without holds/restrictions")
        if category in MERCHANT_CONTACT_CATEGORIES and case.get("contacted_merchant") is not True:
            pc_reasons.append("required merchant contact has not occurred")
        if case.get("pin_compromised") == "yes_shared":
            pc_reasons.append("PIN was voluntarily shared")
        opened = parse_date(account.get("date_opened")) if account else None
        new_account = bool(opened and (today - opened).days < 30)
        if category == "card_not_present_fraud" and new_account:
            pc_reasons.append("card-not-present dispute is on a new account")
        pc_eligible = not pc_reasons
        if pc_eligible:
            deadline = 20 if new_account else 10
            case_notices.append(f"Provisional credit is required if investigation is not resolved promptly; applicable deadline is {deadline} business days.")
        else:
            case_notices.append("Provisional credit is not established as required: " + "; ".join(pc_reasons) + ".")

        if category == "atm_cash_discrepancy":
            if case.get("atm_owner") not in {"rho_bank", "third_party"}:
                blockers.append("ATM ownership must be identified as rho_bank or third_party.")
            elif case.get("atm_owner") == "third_party":
                case_notices.append("Submit the third-party ATM chargeback request; investigation may take up to 90 days.")
            if isinstance(amount, (int, float)) and amount > 200:
                case_notices.append("Send the EFT Error Resolution Affidavit and explain its 10-business-day return deadline and false-statement warning.")

        if blockers:
            blocked.append({"case_id": cid, "blockers": blockers, "notices": case_notices})
            continue

        filing = {
            "transaction_id": txn["transaction_id"],
            "account_id": case["account_id"],
            "card_id": case["card_id"],
            "user_id": state["user_id"],
            "dispute_category": category,
            "transaction_date": mmddyyyy(txn["date"]),
            "discovery_date": discovery,
            "disputed_amount": float(amount),
            "transaction_type": case["transaction_type"],
            "card_in_possession": case["card_in_possession"],
            "pin_compromised": case["pin_compromised"],
            "contacted_merchant": bool(case.get("contacted_merchant")),
            "police_report_filed": police,
            "written_statement_provided": case["written_statement_provided"],
            "provisional_credit_eligible": pc_eligible,
            "card_action": ACTIONS[category],
        }
        ready.append({"case_id": cid, "filing_arguments": filing, "notices": case_notices})
        notices.extend({"case_id": cid, "notice": msg} for msg in case_notices)
        scheduled_by_account[case["account_id"]] = scheduled_by_account.get(case["account_id"], 0) + 1
        action = ACTIONS[category]
        old = card_actions.get(case["card_id"], "keep_active")
        if SEVERITY[action] > SEVERITY[old]:
            card_actions[case["card_id"]] = action
        else:
            card_actions.setdefault(case["card_id"], old)

    action_list = [
        {"card_id": card_id, "actual_card_action_after_successful_filings": action}
        for card_id, action in sorted(card_actions.items())
    ]
    print(json.dumps({
        "ready_filings": ready,
        "blocked_cases": blocked,
        "notices": notices,
        "card_actions": action_list,
        "global_blockers": global_blockers,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        main(payload)
    except Exception as exc:
        output_error("Invalid planning input: " + str(exc))
