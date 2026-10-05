#!/usr/bin/env python3
"""Create a validated, non-executing debit-dispute filing plan.
Reads one JSON object from stdin and writes one JSON object to stdout. Standard library only.
"""
import json
import sys
from datetime import datetime

FMT = "%m/%d/%Y"
CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
TIERS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
OPEN_DISPUTES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
                 "atm_cash_discrepancy", "duplicate_charge"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def date_of(value):
    if not isinstance(value, str):
        raise ValueError("date must be MM/DD/YYYY")
    return datetime.strptime(value, FMT).date()


def tier_of(value):
    value = str(value or "").strip().upper()
    for tier in TIERS:
        if value == tier or value.startswith(tier + " ") or value.startswith(tier + "_"):
            return tier
    return None


def append_once(items, message):
    if message not in items:
        items.append(message)


def provisional(claim, account, transaction, today):
    """Return eligibility and explanatory notices without inventing a statement date."""
    category = claim["category"]
    notices = []
    if category not in PC_CATEGORIES:
        return False, ["This category does not require provisional credit."]
    if claim["written_statement_provided"] is not True:
        return False, ["A written statement has not been provided."]
    if account.get("status") != "OPEN" or account.get("has_holds_or_restrictions") is True:
        return False, ["OPEN unrestricted account standing is not established."]
    if claim["pin_compromised"] == "yes_shared":
        return False, ["The PIN was voluntarily shared."]
    if category == "card_not_present_fraud":
        try:
            if (today - date_of(account.get("date_opened"))).days < 30:
                return False, ["A new-account card-not-present claim does not require provisional credit."]
        except Exception:
            notices.append("Account opening date unavailable; new-account exception could not be evaluated.")
    reported = claim.get("reported_within_60_days_of_statement")
    if reported is False:
        return False, ["Reporting was not within 60 days of the statement."]
    if reported is None:
        # The unavailable statement date is not a filing blocker. Recent transaction and
        # discovery reporting are the available operational evidence for this field.
        try:
            age = (today - date_of(transaction["date"])).days
            discovery_age = (today - date_of(claim["discovery_date"])).days
            if 0 <= age <= 60 and 0 <= discovery_age <= 60:
                notices.append("Statement date unavailable; recent transaction and discovery reporting support provisional-credit eligibility.")
            else:
                return False, ["Timely reporting is not established from statement or recent reporting facts."]
        except Exception:
            return False, ["Timely reporting could not be evaluated."]
    return True, notices


def main(data):
    out = {"ready_filings": [], "blocked_claims": [], "questions": [], "notices": [], "post_filing_actions": []}
    try:
        today = date_of(data.get("today"))
    except Exception:
        out["questions"].append("Provide today's date in MM/DD/YYYY format.")
        return out
    if data.get("verified") is not True:
        out["questions"].append("Complete and log two-factor identity verification before filing.")
        return out

    user_id = data.get("user_id")
    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    transactions = {x.get("transaction_id"): x for x in data.get("transactions", []) if x.get("transaction_id")}
    used = {}
    for dispute in data.get("disputes", []):
        if dispute.get("status") in OPEN_DISPUTES:
            aid = dispute.get("account_id")
            used[aid] = used.get(aid, 0) + 1
    planned = {}
    per_card = {}

    required = ("transaction_id", "account_id", "card_id", "category", "transaction_type",
                "discovery_date", "disputed_amount", "card_in_possession", "pin_compromised",
                "contacted_merchant", "police_report_filed", "written_statement_provided", "atm_owner")
    for number, claim in enumerate(data.get("claims", []), 1):
        label = claim.get("transaction_id") or "claim #" + str(number)
        errors = []
        missing = [field for field in required if claim.get(field) is None]
        if missing:
            errors.append("Collect required fields: " + ", ".join(missing) + ".")
        tx = transactions.get(claim.get("transaction_id"))
        account = accounts.get(claim.get("account_id"))
        card = cards.get(claim.get("card_id"))
        if not tx: errors.append("Transaction was not found in supplied account transaction records.")
        if not account: errors.append("Selected account was not found.")
        if not card: errors.append("Selected debit card was not found.")
        if claim.get("category") not in CATEGORIES: errors.append("Use a supported dispute category.")
        if claim.get("transaction_type") not in TYPES: errors.append("Use a supported transaction type.")
        if claim.get("pin_compromised") not in PINS: errors.append("Use a permitted PIN-compromise value.")
        if claim.get("atm_owner") not in {"rho_bank", "third_party", "not_atm"}: errors.append("Identify ATM ownership.")
        if not isinstance(claim.get("card_in_possession"), bool): errors.append("Confirm card possession as true or false.")
        for field in ("contacted_merchant", "police_report_filed", "written_statement_provided"):
            if field in claim and not isinstance(claim.get(field), bool): errors.append(field + " must be true or false.")
        if claim.get("reported_within_60_days_of_statement") not in (True, False, None):
            errors.append("reported_within_60_days_of_statement must be true, false, or null.")
        if tx:
            if tx.get("account_id") != claim.get("account_id"): errors.append("Transaction is not on the selected account.")
            try:
                age = (today - date_of(tx.get("date"))).days
                if age < 0 or age > 60: errors.append("Transaction is not within the permitted 60-day filing window.")
                if date_of(claim.get("discovery_date")) > today: errors.append("Discovery date cannot be in the future.")
            except Exception:
                errors.append("Transaction and discovery dates must be MM/DD/YYYY.")
            try:
                full = abs(float(tx.get("amount")))
                amount = float(claim.get("disputed_amount"))
                if full < 1 or amount < 1: errors.append("Transaction and disputed amount must each be at least $1.")
                if amount > full: errors.append("Disputed amount exceeds the transaction amount.")
            except (TypeError, ValueError):
                errors.append("Transaction and disputed amounts must be numeric.")
        if account and card:
            if account.get("account_type", "").lower() != "checking" or account.get("status") != "OPEN": errors.append("An OPEN checking account is required.")
            if card.get("account_id") != claim.get("account_id") or card.get("user_id") != user_id: errors.append("Card/account/user linkage does not match.")
            tier = tier_of(account.get("account_class"))
            if not tier:
                errors.append("Account tier is unavailable for dispute-limit validation.")
            elif used.get(claim["account_id"], 0) + planned.get(claim["account_id"], 0) >= TIERS[tier]:
                errors.append("The account has reached its open-dispute limit.")
        if claim.get("category") in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and claim.get("atm_owner") == "not_atm":
            errors.append("An ATM category requires Rho-Bank or third-party ATM identification.")
        if claim.get("category") == "duplicate_charge":
            ids = claim.get("duplicate_group_transaction_ids")
            if not isinstance(ids, list) or not ids:
                errors.append("Supply duplicate-group transaction IDs to confirm earliest-first filing.")
            elif any(transactions.get(x) is None for x in ids):
                errors.append("Every duplicate-group transaction must be in transaction records.")
            else:
                earliest = min(ids, key=lambda x: date_of(transactions[x]["date"]))
                if earliest != claim.get("transaction_id"): errors.append("File the earliest duplicate transaction first.")
        if errors:
            out["blocked_claims"].append({"claim": label, "reasons": errors})
            continue

        eligible, pc_notices = provisional(claim, account, tx, today)
        action = ACTIONS.get(claim["category"], "keep_active")
        filing = {
            "transaction_id": claim["transaction_id"], "account_id": claim["account_id"], "card_id": claim["card_id"], "user_id": user_id,
            "dispute_category": claim["category"], "transaction_date": tx["date"], "discovery_date": claim["discovery_date"],
            "disputed_amount": float(claim["disputed_amount"]), "transaction_type": claim["transaction_type"],
            "card_in_possession": claim["card_in_possession"], "pin_compromised": claim["pin_compromised"],
            "contacted_merchant": claim["contacted_merchant"], "police_report_filed": claim["police_report_filed"],
            "written_statement_provided": claim["written_statement_provided"], "provisional_credit_eligible": eligible, "card_action": action
        }
        out["ready_filings"].append(filing)
        planned[claim["account_id"]] = planned.get(claim["account_id"], 0) + 1
        for notice in pc_notices: append_once(out["notices"], label + ": " + notice)
        if claim["category"] == "atm_cash_discrepancy" and claim["atm_owner"] == "third_party":
            append_once(out["notices"], label + ": third-party ATM investigation may take up to 90 days.")
        if claim["category"] == "atm_cash_discrepancy" and float(claim["disputed_amount"]) > 200:
            append_once(out["notices"], label + ": provide the EFT Error Resolution Affidavit and 10-business-day return notice.")
        if claim["category"] in {"card_present_fraud", "card_not_present_fraud"} and float(claim["disputed_amount"]) > 500 and not claim["police_report_filed"]:
            append_once(out["notices"], label + ": recommend a police report for suspected fraud above $500.")
        if SEVERITY[action] > SEVERITY.get(per_card.get(claim["card_id"], "keep_active"), 0):
            per_card[claim["card_id"]] = action
        elif claim["card_id"] not in per_card:
            per_card[claim["card_id"]] = action

    for card_id, action in per_card.items():
        if action == "freeze_pending_investigation":
            out["post_filing_actions"].append({"card_id": card_id, "tool": "freeze_debit_card_3892", "action": "freeze", "preconditions": ["verified owner", "ACTIVE card"]})
        elif action == "close_and_reissue":
            out["post_filing_actions"].append({"card_id": card_id, "tool": "close_debit_card_4721", "action": "close_and_reissue", "preconditions": ["verified owner", "closure prerequisites checked"]})
    return out

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ready_filings": [], "blocked_claims": [], "questions": ["Planner input could not be evaluated: " + str(exc)], "notices": [], "post_filing_actions": []}, separators=(",", ":")))
