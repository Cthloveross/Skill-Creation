#!/usr/bin/env python3
"""Preflight validator for debit-card dispute filing payloads.

Reads one JSON object from stdin and writes one JSON object to stdout. This
script has no banking-tool or network side effects.
"""
import json
import sys
from datetime import datetime

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
PC_CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge",
    "card_present_fraud", "card_not_present_fraud",
}
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
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def date_value(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def tier(value):
    text = str(value or "").strip().upper()
    for candidate in LIMITS:
        if text in (candidate, candidate + " TIER"):
            return candidate
    return None


def as_amount(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main(data):
    output = {"global_errors": [], "claims": [], "card_actions": []}
    user_id = data.get("user_id")
    today = date_value(data.get("current_date"))
    if not user_id:
        output["global_errors"].append("user_id is required")
    if not data.get("verified"):
        output["global_errors"].append("customer identity has not been verified")
    if not today:
        output["global_errors"].append("current_date must use MM/DD/YYYY")

    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    transactions = {x.get("transaction_id"): x for x in data.get("transactions", []) if x.get("transaction_id")}
    open_counts = {}
    for dispute in data.get("existing_disputes", []):
        if str(dispute.get("status", "")).upper() == "OPEN" and dispute.get("account_id"):
            aid = dispute["account_id"]
            open_counts[aid] = open_counts.get(aid, 0) + 1

    planned_counts = {}
    best_actions = {}
    for number, claim in enumerate(data.get("claims", []), 1):
        errors, warnings, pc_reasons = [], [], []
        txn = transactions.get(claim.get("transaction_id"))
        account = accounts.get(claim.get("account_id"))
        card = cards.get(claim.get("card_id"))
        category = claim.get("dispute_category")
        tx_type = claim.get("transaction_type")
        discovery = date_value(claim.get("discovery_date"))

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
                errors.append("debit-card disputes require a checking account")
            if str(account.get("status", "")).upper() != "OPEN":
                errors.append("linked checking account is not OPEN")
            if not tier(account.get("account_class")):
                errors.append("account tier is missing or unsupported; open-dispute capacity cannot be verified")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        if tx_type not in TYPES:
            errors.append("transaction_type is invalid")
        if not discovery:
            errors.append("discovery_date must use MM/DD/YYYY")
        elif today and discovery > today:
            errors.append("discovery_date cannot be in the future")
        if claim.get("pin_compromised") not in PINS:
            errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown")
        for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
            if not isinstance(claim.get(field), bool):
                errors.append(field + " must be a boolean")

        amount = as_amount(claim.get("disputed_amount"))
        if amount is None or amount <= 0:
            errors.append("disputed_amount must be a positive number")
        txn_date = date_value(txn.get("date")) if txn else None
        source_amount = as_amount(txn.get("amount")) if txn else None
        if txn and not txn_date:
            errors.append("source transaction date is invalid")
        if txn_date and today:
            if txn_date > today:
                errors.append("transaction date cannot be in the future")
            elif (today - txn_date).days > 60:
                errors.append("transaction is more than 60 days old")
        if source_amount is None and txn:
            errors.append("source transaction amount is invalid")
        elif source_amount is not None:
            if abs(source_amount) < 1:
                errors.append("source transaction amount is below $1.00")
            if amount is not None and amount > abs(source_amount):
                errors.append("disputed_amount cannot exceed the source transaction amount")

        if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal":
            errors.append("ATM cash discrepancy requires transaction_type atm_withdrawal")
        if category == "atm_deposit_not_credited" and tx_type != "atm_deposit":
            errors.append("ATM deposit dispute requires transaction_type atm_deposit")
        if category == "card_not_present_fraud" and tx_type != "online_purchase":
            errors.append("card-not-present fraud requires transaction_type online_purchase")
        if category == "recurring_charge_after_cancellation" and tx_type != "recurring_payment":
            errors.append("recurring-charge dispute requires transaction_type recurring_payment")

        atm_owner = claim.get("atm_owner", "not_applicable")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
            if atm_owner not in {"rho_bank", "third_party"}:
                errors.append("ATM disputes require atm_owner rho_bank or third_party")
            elif atm_owner == "rho_bank":
                warnings.append("Review Rho-Bank journal records or deposit images before filing")
            else:
                warnings.append("Third-party ATM claim requires network/owner chargeback handling and may take up to 90 days")
                if category == "atm_cash_discrepancy" and amount is not None and amount > 200:
                    warnings.append("Explain the required Electronic Fund Transfer Error Resolution Affidavit")
        elif atm_owner not in (None, "", "not_applicable"):
            warnings.append("atm_owner is ignored for a non-ATM claim")

        if category == "duplicate_charge":
            group = claim.get("duplicate_group_transaction_ids")
            if not isinstance(group, list) or not group:
                errors.append("duplicate disputes require duplicate_group_transaction_ids")
            else:
                group_records = [transactions.get(tid) for tid in group]
                if any(record is None for record in group_records):
                    errors.append("duplicate group contains an unknown transaction")
                else:
                    dated = [(date_value(record.get("date")), record.get("transaction_id")) for record in group_records]
                    if any(day is None for day, _ in dated):
                        errors.append("duplicate group contains an invalid transaction date")
                    elif claim.get("transaction_id") != min(dated)[1]:
                        errors.append("file the earliest transaction in a duplicate group first")

        account_tier = tier(account.get("account_class")) if account else None
        if account_tier:
            account_id = account.get("account_id")
            used = open_counts.get(account_id, 0) + planned_counts.get(account_id, 0)
            if used >= LIMITS[account_tier]:
                errors.append("maximum open disputes reached for this account tier")

        timely = claim.get("timely_reported_within_60_statement_days")
        if not isinstance(timely, bool):
            timely = False
            warnings.append("statement-based timely-reporting status is unknown")
        no_restrictions = bool(account) and account.get("has_holds_or_restrictions") is False
        if account and "has_holds_or_restrictions" not in account:
            warnings.append("account hold/restriction status is unknown; provisional-credit eligibility cannot be confirmed")
        opened = date_value(account.get("date_opened")) if account else None
        new_account = bool(today and opened and (today - opened).days < 30)
        if account and not opened:
            warnings.append("account opening date is unknown; new-account provisional-credit rule cannot be checked")

        pc = bool(category in PC_CATEGORIES and timely and claim.get("written_statement_provided") and no_restrictions)
        if category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is False:
            pc = False
            pc_reasons.append("merchant was not contacted for this non-fraud claim")
        if claim.get("pin_compromised") == "yes_shared":
            pc = False
            pc_reasons.append("PIN was voluntarily shared")
        if category == "card_not_present_fraud" and new_account:
            pc = False
            pc_reasons.append("card-not-present claim is on a new account")
        if pc:
            pc_reasons.append("timely eligible category, written statement, and open unrestricted account are confirmed")
        elif not pc_reasons:
            pc_reasons.append("one or more provisional-credit conditions are not confirmed")

        if category in {"card_present_fraud", "card_not_present_fraud"} and amount is not None and amount > 500 and claim.get("police_report_filed") is False:
            warnings.append("recommend a police report for suspected fraud over $500")

        action = ACTIONS.get(category)
        payload = None
        if not errors and action:
            account_id = claim.get("account_id")
            planned_counts[account_id] = planned_counts.get(account_id, 0) + 1
            payload = {
                "transaction_id": claim.get("transaction_id"), "account_id": account_id,
                "card_id": claim.get("card_id"), "user_id": user_id,
                "dispute_category": category, "transaction_date": txn.get("date"),
                "discovery_date": claim.get("discovery_date"), "disputed_amount": amount,
                "transaction_type": tx_type, "card_in_possession": claim.get("card_in_possession"),
                "pin_compromised": claim.get("pin_compromised"),
                "contacted_merchant": claim.get("contacted_merchant"),
                "police_report_filed": claim.get("police_report_filed"),
                "written_statement_provided": claim.get("written_statement_provided"),
                "provisional_credit_eligible": pc, "card_action": action,
            }
            prior = best_actions.get(claim.get("card_id"), "keep_active")
            if SEVERITY[action] >= SEVERITY[prior]:
                best_actions[claim.get("card_id")] = action

        output["claims"].append({
            "claim_number": number,
            "errors": errors,
            "warnings": warnings,
            "liability_disclosure": "Give the applicable $50 / $500 / unlimited Regulation E disclosure before filing.",
            "provisional_credit_eligible": pc,
            "provisional_credit_reasoning": pc_reasons,
            "filing_payload": payload,
        })

    output["card_actions"] = [
        {"card_id": card_id, "post_filing_action": action}
        for card_id, action in best_actions.items()
    ]
    return output


if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
