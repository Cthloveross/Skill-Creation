#!/usr/bin/env python3
"""Validate runtime debit-dispute records and produce a non-executing filing plan.
Input and output are JSON objects on stdin/stdout; only the Python standard library is used.
"""
import json
import sys
from datetime import datetime, date

DATE_FMT = "%m/%d/%Y"
CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
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
TIERS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
REQUIRED_PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
NO_REQUIRED_PC_CATEGORIES = {"goods_services_not_received", "recurring_charge_after_cancellation", "atm_deposit_not_credited", "incorrect_amount"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be MM/DD/YYYY")
    return datetime.strptime(value, DATE_FMT).date()

def add_unique(target, message):
    if message not in target:
        target.append(message)

def normalized_tier(value):
    text = str(value or "").strip().upper()
    for tier in TIERS:
        if text == tier or text.startswith(tier + " ") or text.startswith(tier + "_"):
            return tier
    return None

def pc_result(claim, account, today):
    """Return (boolean, explanatory list); never presume unknown conditions."""
    reasons = []
    category = claim.get("category")
    if claim.get("reported_within_60_days_of_statement") is not True:
        reasons.append("Timely reporting within 60 days of the statement is not established.")
    if category not in REQUIRED_PC_CATEGORIES:
        reasons.append("This dispute category does not require provisional credit.")
    if claim.get("written_statement_provided") is not True:
        reasons.append("A written statement has not been provided.")
    if account.get("status") != "OPEN":
        reasons.append("The checking account is not OPEN.")
    if account.get("has_holds_or_restrictions") is not False:
        reasons.append("Clear account standing (no hold or restriction) is not established.")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is not True:
        reasons.append("Merchant/ATM-operator contact has not occurred for this non-fraud dispute.")
    if claim.get("pin_compromised") == "yes_shared":
        reasons.append("The PIN was voluntarily shared.")
    try:
        new_account = (today - parse_date(account.get("date_opened"))).days < 30
    except Exception:
        new_account = None
        reasons.append("Account opening date is unavailable to evaluate new-account rules.")
    if new_account and category == "card_not_present_fraud":
        reasons.append("A new-account card-not-present dispute does not require provisional credit.")
    return (not reasons), reasons

def main(data):
    output = {"ready_filings": [], "blocked_claims": [], "questions": [], "notices": [], "post_filing_actions": []}
    try:
        today = parse_date(data.get("today"))
    except Exception:
        output["questions"].append("Provide today's date in MM/DD/YYYY format.")
        return output
    if data.get("verified") is not True:
        output["questions"].append("Complete two-factor identity verification and log it before filing.")
        return output
    user_id = data.get("user_id")
    accounts = {a.get("account_id"): a for a in data.get("accounts", []) if a.get("account_id")}
    cards = {c.get("card_id"): c for c in data.get("cards", []) if c.get("card_id")}
    transactions = {t.get("transaction_id"): t for t in data.get("transactions", []) if t.get("transaction_id")}
    open_count = {}
    for dispute in data.get("disputes", []):
        if dispute.get("status") in OPEN_STATUSES:
            account_id = dispute.get("account_id")
            open_count[account_id] = open_count.get(account_id, 0) + 1
    planned_per_account = {}
    per_card_action = {}

    for index, claim in enumerate(data.get("claims", []), 1):
        label = claim.get("transaction_id") or "claim #" + str(index)
        errors = []
        missing = []
        required = ["transaction_id", "card_id", "account_id", "category", "transaction_type", "discovery_date",
                    "disputed_amount", "card_in_possession", "pin_compromised", "contacted_merchant",
                    "police_report_filed", "written_statement_provided", "reported_within_60_days_of_statement", "atm_owner"]
        for key in required:
            if key not in claim or claim.get(key) is None:
                missing.append(key)
        if missing:
            errors.append("Collect required claim fields: " + ", ".join(missing) + ".")
        transaction = transactions.get(claim.get("transaction_id"))
        card = cards.get(claim.get("card_id"))
        account = accounts.get(claim.get("account_id"))
        if not transaction:
            errors.append("Transaction ID was not found in the supplied account transactions.")
        if not card:
            errors.append("Debit card was not found.")
        if not account:
            errors.append("Checking account was not found.")
        if claim.get("category") not in CATEGORIES:
            errors.append("Use a supported dispute category.")
        if claim.get("transaction_type") not in TYPES:
            errors.append("Use a supported transaction_type.")
        if claim.get("pin_compromised") not in PINS:
            errors.append("Collect one permitted PIN-compromise response.")
        if claim.get("atm_owner") not in {"rho_bank", "third_party", "not_atm"}:
            errors.append("Identify ATM ownership as rho_bank, third_party, or not_atm.")
        if not isinstance(claim.get("card_in_possession"), bool):
            errors.append("Confirm whether the physical card is in the customer's possession.")
        for field in ("contacted_merchant", "police_report_filed", "written_statement_provided", "reported_within_60_days_of_statement"):
            if field in claim and not isinstance(claim.get(field), bool):
                errors.append(field + " must be true or false.")
        if transaction:
            if transaction.get("account_id") != claim.get("account_id"):
                errors.append("Transaction does not belong to the selected account.")
            try:
                age = (today - parse_date(transaction.get("date"))).days
                if age < 0:
                    errors.append("Transaction date cannot be in the future.")
                elif age > 60:
                    errors.append("Transaction is more than 60 days old and cannot be filed under this procedure.")
            except Exception:
                errors.append("Transaction date must be MM/DD/YYYY.")
            try:
                transaction_amount = abs(float(transaction.get("amount")))
                disputed_amount = float(claim.get("disputed_amount"))
                if transaction_amount < 1:
                    errors.append("The transaction amount is below the $1 minimum.")
                if disputed_amount < 1:
                    errors.append("The disputed amount must be at least $1.")
                if disputed_amount > transaction_amount:
                    errors.append("The disputed amount exceeds the transaction amount.")
            except (TypeError, ValueError):
                errors.append("Transaction and disputed amounts must be numeric.")
        if card and account:
            if card.get("account_id") != claim.get("account_id"):
                errors.append("Card is not linked to the selected account.")
            if card.get("user_id") != user_id:
                errors.append("Card does not belong to the verified user.")
            if account.get("account_type", "").lower() != "checking" or account.get("status") != "OPEN":
                errors.append("A debit dispute requires an OPEN checking account linked to the card.")
            tier = normalized_tier(account.get("account_class"))
            if not tier:
                errors.append("Account tier is missing or unsupported; cannot evaluate its dispute limit.")
            else:
                used = open_count.get(account.get("account_id"), 0) + planned_per_account.get(account.get("account_id"), 0)
                if used >= TIERS[tier]:
                    errors.append("This account has reached its maximum open-dispute limit (" + str(TIERS[tier]) + ").")
        if claim.get("category") == "duplicate_charge":
            duplicate_ids = claim.get("duplicate_group_transaction_ids")
            if not isinstance(duplicate_ids, list) or not duplicate_ids:
                errors.append("Provide all duplicate-group transaction IDs to confirm the earliest duplicate is filed first.")
            else:
                candidates = [transactions.get(x) for x in duplicate_ids]
                if any(x is None for x in candidates):
                    errors.append("Every duplicate-group transaction ID must be present in transaction records.")
                else:
                    earliest = min(candidates, key=lambda x: parse_date(x.get("date"))).get("transaction_id")
                    if claim.get("transaction_id") != earliest:
                        errors.append("Duplicate disputes must be filed against the earliest transaction first.")
        if claim.get("category") in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and claim.get("atm_owner") == "not_atm":
            errors.append("ATM dispute category requires ATM ownership identification.")
        if errors:
            output["blocked_claims"].append({"claim": label, "reasons": errors})
            continue
        # A claim that passed all filing prerequisites consumes capacity for subsequent claims.
        account_id = claim["account_id"]
        planned_per_account[account_id] = planned_per_account.get(account_id, 0) + 1
        action = ACTIONS[claim["category"]]
        eligible, pc_reasons = pc_result(claim, account, today)
        filing = {
            "transaction_id": claim["transaction_id"], "account_id": account_id, "card_id": claim["card_id"], "user_id": user_id,
            "dispute_category": claim["category"], "transaction_date": transaction["date"],
            "discovery_date": claim["discovery_date"], "disputed_amount": float(claim["disputed_amount"]),
            "transaction_type": claim["transaction_type"], "card_in_possession": claim["card_in_possession"],
            "pin_compromised": claim["pin_compromised"], "contacted_merchant": claim["contacted_merchant"],
            "police_report_filed": claim["police_report_filed"], "written_statement_provided": claim["written_statement_provided"],
            "provisional_credit_eligible": eligible, "card_action": action
        }
        output["ready_filings"].append(filing)
        if eligible:
            add_unique(output["notices"], label + ": provisional credit is required when the investigation exceeds the initial period; use the applicable 10-business-day (20 for new accounts) timeline.")
        else:
            add_unique(output["notices"], label + ": provisional credit is not established as required: " + " ".join(pc_reasons))
        if claim["category"] in {"card_present_fraud", "card_not_present_fraud"} and float(claim["disputed_amount"]) > 500 and not claim["police_report_filed"]:
            add_unique(output["notices"], label + ": recommend filing a police report because suspected fraud exceeds $500.")
        if claim["category"] == "atm_cash_discrepancy":
            if claim["atm_owner"] == "third_party":
                add_unique(output["notices"], label + ": submit a third-party ATM/network chargeback; investigation may take up to 90 days.")
            elif claim["atm_owner"] == "rho_bank":
                add_unique(output["notices"], label + ": inspect Rho-Bank ATM journal evidence before communicating whether an immediate provisional credit is supported.")
            if float(claim["disputed_amount"]) > 200:
                add_unique(output["notices"], label + ": send the EFT Error Resolution Affidavit to the registered email; it must be returned within 10 business days and false signing is a federal offense.")
        if claim["category"] == "atm_deposit_not_credited" and claim["atm_owner"] == "rho_bank":
            add_unique(output["notices"], label + ": retrieve ATM deposit images; physical verification may take up to 45 days.")
        if claim["category"] == "recurring_charge_after_cancellation":
            add_unique(output["notices"], label + ": ask whether the customer wants all recurring payments blocked after this past-charge dispute is filed.")
        card_id = claim["card_id"]
        if SEVERITY[action] > SEVERITY.get(per_card_action.get(card_id, "keep_active"), 0):
            per_card_action[card_id] = action
        elif card_id not in per_card_action:
            per_card_action[card_id] = action

    for card_id, action in per_card_action.items():
        if action == "freeze_pending_investigation":
            output["post_filing_actions"].append({"card_id": card_id, "action": "freeze", "tool": "freeze_debit_card_3892", "preconditions": ["verified owner", "card status ACTIVE" ]})
        elif action == "close_and_reissue":
            output["post_filing_actions"].append({"card_id": card_id, "action": "close_and_reissue", "tool": "close_debit_card_4721", "preconditions": ["verified owner", "ACTIVE or PENDING card", "pending transaction/refund and closure requirements checked; fraud security exception may bypass age" ]})
    return output

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready_filings": [], "blocked_claims": [], "questions": ["Planner input could not be evaluated: " + str(exc)], "notices": [], "post_filing_actions": []}, separators=(",", ":")))
