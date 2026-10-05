#!/usr/bin/env python3
"""Validate debit-card dispute claims and produce filing/action plans.

Reads a JSON object from stdin and writes one JSON object to stdout.  It has no
network or tool side effects.  See SKILL.md for the input schema.
"""
import json
import sys
from datetime import datetime, date

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
TIER_LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud",
    "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge",
}
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
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def tier_name(value):
    text = str(value or "").strip().upper()
    for tier in TIER_LIMITS:
        if text == tier or text == tier + " TIER":
            return tier
    return None


def is_open_dispute(item):
    return str(item.get("status", "")).upper() == "OPEN"


def main(data):
    output = {"claims": [], "card_actions": [], "global_errors": []}
    user_id = data.get("user_id")
    current = parse_date(data.get("current_date"))
    if not current:
        output["global_errors"].append("current_date must use MM/DD/YYYY")
    if not data.get("verified"):
        output["global_errors"].append("Customer identity has not been verified")
    if not user_id:
        output["global_errors"].append("user_id is required")

    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    transactions = {x.get("transaction_id"): x for x in data.get("transactions", []) if x.get("transaction_id")}
    open_counts = {}
    for d in data.get("existing_disputes", []):
        if is_open_dispute(d) and d.get("account_id"):
            aid = d["account_id"]
            open_counts[aid] = open_counts.get(aid, 0) + 1

    planned_counts = {}
    best_actions = {}
    for index, claim in enumerate(data.get("claims", []), start=1):
        errors, warnings, reasons = [], [], []
        txn = transactions.get(claim.get("transaction_id"))
        account = accounts.get(claim.get("account_id"))
        card = cards.get(claim.get("card_id"))
        category = claim.get("dispute_category")
        tx_type = claim.get("transaction_type")
        discovery = parse_date(claim.get("discovery_date"))

        if not txn:
            errors.append("transaction_id was not found in supplied transaction records")
        if not account:
            errors.append("account_id was not found in supplied account records")
        if not card:
            errors.append("card_id was not found in supplied card records")
        if txn and txn.get("account_id") != claim.get("account_id"):
            errors.append("transaction does not belong to the selected account")
        if card and (card.get("account_id") != claim.get("account_id") or card.get("user_id") != user_id):
            errors.append("card does not belong to the verified user and selected account")
        if account:
            if str(account.get("account_type", "")).lower() != "checking":
                errors.append("debit cards and debit disputes require a checking account")
            if str(account.get("status", "")).upper() != "OPEN":
                errors.append("linked checking account is not OPEN")
            if not tier_name(account.get("account_class")):
                errors.append("account tier is missing or unsupported; dispute limit cannot be verified")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        if tx_type not in TRANSACTION_TYPES:
            errors.append("transaction_type is invalid")
        if not discovery:
            errors.append("discovery_date must use MM/DD/YYYY")
        if current and discovery and discovery > current:
            errors.append("discovery_date cannot be in the future")
        if claim.get("pin_compromised") not in PINS:
            errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown")
        for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
            if not isinstance(claim.get(field), bool):
                errors.append(field + " must be a boolean")

        amount = claim.get("disputed_amount")
        try:
            amount = float(amount)
            if amount <= 0:
                errors.append("disputed_amount must be greater than zero")
        except (TypeError, ValueError):
            amount = None
            errors.append("disputed_amount must be numeric")
        txn_date = parse_date(txn.get("date")) if txn else None
        if txn and not txn_date:
            errors.append("source transaction date is invalid")
        if txn_date and current and (current - txn_date).days > 60:
            errors.append("transaction is more than 60 days old")
        if txn_date and current and txn_date > current:
            errors.append("transaction date cannot be in the future")
        if txn:
            try:
                txn_amount = abs(float(txn.get("amount")))
                if txn_amount < 1:
                    errors.append("transaction amount is below $1.00")
                if amount is not None and amount > txn_amount:
                    errors.append("disputed_amount cannot exceed the source transaction amount")
            except (TypeError, ValueError):
                errors.append("source transaction amount is invalid")

        if category in {"card_present_fraud", "card_not_present_fraud"} and amount is not None and amount > 500:
            if claim.get("police_report_filed") is False:
                warnings.append("Recommend a police report for suspected fraud over $500")
        if category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is False:
            warnings.append("Merchant was not contacted; this prevents required provisional credit for a non-fraud claim")

        atm_owner = claim.get("atm_owner", "not_applicable")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
            if atm_owner not in {"rho_bank", "third_party"}:
                errors.append("ATM disputes require atm_owner of rho_bank or third_party")
            elif atm_owner == "rho_bank":
                warnings.append("Review Rho-Bank ATM journal records or deposit images before filing")
            elif atm_owner == "third_party":
                warnings.append("Submit a chargeback request to the third-party ATM owner/network; investigation may take up to 90 days")
                if category == "atm_cash_discrepancy" and amount is not None and amount > 200:
                    warnings.append("Electronic Fund Transfer Error Resolution Affidavit is required within 10 business days")
        elif atm_owner not in {None, "", "not_applicable"}:
            warnings.append("atm_owner is ignored for a non-ATM dispute")

        if category == "duplicate_charge":
            group = claim.get("duplicate_group_transaction_ids")
            if not isinstance(group, list) or not group:
                errors.append("duplicate disputes require duplicate_group_transaction_ids to verify the earliest transaction")
            else:
                group_txns = [transactions.get(tid) for tid in group]
                if any(t is None for t in group_txns):
                    errors.append("duplicate group contains an unknown transaction")
                else:
                    dated = [(parse_date(t.get("date")), t.get("transaction_id")) for t in group_txns]
                    if any(d is None for d, _ in dated):
                        errors.append("duplicate group contains an invalid transaction date")
                    else:
                        earliest = min(dated)[1]
                        if claim.get("transaction_id") != earliest:
                            errors.append("file the earliest transaction in a duplicate group first")

        tier = tier_name(account.get("account_class")) if account else None
        if tier:
            used = open_counts.get(account.get("account_id"), 0) + planned_counts.get(account.get("account_id"), 0)
            if used >= TIER_LIMITS[tier]:
                errors.append("maximum open disputes reached for this account tier")

        timely = claim.get("timely_reported_within_60_statement_days")
        if not isinstance(timely, bool):
            warnings.append("Statement-based timely-reporting status is unknown; exact liability and provisional-credit eligibility cannot be confirmed")
            timely = False
        no_holds = bool(account) and account.get("has_holds_or_restrictions") is False
        if account and "has_holds_or_restrictions" not in account:
            warnings.append("Account hold/restriction status is unknown")
        new_account = False
        opened = parse_date(account.get("date_opened")) if account else None
        if account and not opened:
            warnings.append("Account opening date is unknown; new-account provisional-credit rule cannot be checked")
        elif opened and current:
            new_account = (current - opened).days < 30
        pc = (category in PC_CATEGORIES and timely and bool(claim.get("written_statement_provided")) and no_holds)
        if category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is False:
            pc = False
            reasons.append("merchant-contact condition not met for non-fraud claim")
        if claim.get("pin_compromised") == "yes_shared":
            pc = False
            reasons.append("PIN was voluntarily shared")
        if category == "card_not_present_fraud" and new_account:
            pc = False
            reasons.append("card-not-present claim on a new account")
        if not pc and not reasons:
            reasons.append("one or more required provisional-credit conditions are not met")
        if pc:
            reasons.append("timely eligible category, written statement, and open unrestricted account confirmed")

        action = CARD_ACTIONS.get(category)
        payload = None
        if not errors and action:
            planned_counts[account.get("account_id")] = planned_counts.get(account.get("account_id"), 0) + 1
            payload = {
                "transaction_id": claim.get("transaction_id"), "account_id": claim.get("account_id"),
                "card_id": claim.get("card_id"), "user_id": user_id,
                "dispute_category": category, "transaction_date": txn.get("date"),
                "discovery_date": claim.get("discovery_date"), "disputed_amount": amount,
                "transaction_type": tx_type, "card_in_possession": claim.get("card_in_possession"),
                "pin_compromised": claim.get("pin_compromised"), "contacted_merchant": claim.get("contacted_merchant"),
                "police_report_filed": claim.get("police_report_filed"),
                "written_statement_provided": claim.get("written_statement_provided"),
                "provisional_credit_eligible": pc, "card_action": action,
            }
            prior = best_actions.get(claim.get("card_id"), "keep_active")
            if SEVERITY[action] > SEVERITY[prior]:
                best_actions[claim.get("card_id")] = action
            elif claim.get("card_id") not in best_actions:
                best_actions[claim.get("card_id")] = action
        output["claims"].append({
            "claim_number": index, "errors": errors, "warnings": warnings,
            "liability_disclosure": "Give the applicable $50 / $500 / unlimited liability disclosure before filing.",
            "provisional_credit_eligible": pc, "provisional_credit_reasoning": reasons,
            "filing_payload": payload,
        })

    output["card_actions"] = [
        {"card_id": card_id, "post_filing_action": action}
        for card_id, action in best_actions.items()
    ]
    return output


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
