#!/usr/bin/env python3
"""Validate supplied debit-dispute facts; JSON stdin to JSON stdout.

Input schema is documented in SKILL.md.  `reference_date`, transaction_date, and
 discovery_date use MM/DD/YYYY. Output has `disputes` in input order and
 `card_actions`, keyed by card_id. This program makes no bank calls.
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
LIMITS = {"Entry Tier": 2, "Mid Tier": 3, "Premium Tier": 4, "Elite Tier": 5}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active",
    "recurring_charge_after_cancellation": "keep_active",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud",
                 "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}


def date_value(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be an MM/DD/YYYY string")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{field} must be a valid MM/DD/YYYY date")
        return None


def boolean(value, field, errors):
    if not isinstance(value, bool):
        errors.append(f"{field} must be boolean")
        return False
    return value


def main(data):
    top_errors = []
    reference = date_value(data.get("reference_date"), "reference_date", top_errors)
    tiers = data.get("tier_by_account", {})
    existing = data.get("open_disputes_by_account", {})
    claims = data.get("disputes", [])
    if not isinstance(tiers, dict):
        top_errors.append("tier_by_account must be an object")
        tiers = {}
    if not isinstance(existing, dict):
        top_errors.append("open_disputes_by_account must be an object")
        existing = {}
    if not isinstance(claims, list):
        top_errors.append("disputes must be an array")
        claims = []

    accepted_per_account = {}
    results = []
    by_card = {}
    for index, claim in enumerate(claims):
        errors, warnings = [], []
        if not isinstance(claim, dict):
            results.append({"index": index, "fileable": False, "errors": ["claim must be an object"], "warnings": []})
            continue
        required_ids = ("account_id", "transaction_id", "card_id", "user_id")
        for key in required_ids:
            if not isinstance(claim.get(key), str) or not claim[key]:
                errors.append(f"{key} is required")
        account_id = claim.get("account_id")
        card_id = claim.get("card_id")
        category = claim.get("category")
        if category not in CATEGORIES:
            errors.append("category is not an allowed dispute category")
        transaction_type = claim.get("transaction_type")
        if transaction_type not in TYPES:
            errors.append("transaction_type is not an allowed transaction type")
        if claim.get("pin_compromised") not in PINS:
            errors.append("pin_compromised is invalid")
        for field in ("card_in_possession", "contacted_merchant", "police_report_filed",
                      "written_statement_provided", "reported_within_60_days_of_statement",
                      "account_open", "account_has_holds_or_restrictions",
                      "card_linked_to_open_checking", "transaction_confirmed"):
            boolean(claim.get(field), field, errors)
        tx_date = date_value(claim.get("transaction_date"), "transaction_date", errors)
        date_value(claim.get("discovery_date"), "discovery_date", errors)
        if tx_date and reference:
            age = (reference - tx_date).days
            if age < 0:
                errors.append("transaction_date cannot be after reference_date")
            elif age > 60:
                errors.append("transaction is more than 60 days old")
        amount = claim.get("transaction_amount")
        disputed = claim.get("disputed_amount")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
            errors.append("transaction_amount must be numeric and at least 1.00")
        if not isinstance(disputed, (int, float)) or isinstance(disputed, bool) or disputed < 1:
            errors.append("disputed_amount must be numeric and at least 1.00")
        elif isinstance(amount, (int, float)) and not isinstance(amount, bool) and disputed > abs(amount):
            errors.append("disputed_amount cannot exceed transaction_amount")
        if not claim.get("transaction_confirmed"):
            errors.append("transaction must be confirmed from account history")
        if not claim.get("account_open") or not claim.get("card_linked_to_open_checking"):
            errors.append("card must be linked to an OPEN checking account")
        if category == "duplicate_charge" and claim.get("is_earliest_duplicate") is not True:
            errors.append("duplicate claim must identify the earliest duplicate transaction")
        if category in {"card_present_fraud", "card_not_present_fraud"} and claim.get("card_in_possession") is not True:
            warnings.append("fraud card-possession response needs follow-up/card-security review")
        if category == "card_present_fraud" and transaction_type not in {"pin_purchase", "signature_purchase"}:
            warnings.append("verify physical-card transaction type matches fraud classification")
        if category == "card_not_present_fraud" and transaction_type not in {"online_purchase", "recurring_payment"}:
            warnings.append("verify card-not-present transaction type matches fraud classification")
        if category not in {"card_present_fraud", "card_not_present_fraud"} and not claim.get("contacted_merchant"):
            warnings.append("merchant has not been contacted; record this and advise contact")
        if category in {"card_present_fraud", "card_not_present_fraud"} and isinstance(disputed, (int, float)) and disputed > 500 and not claim.get("police_report_filed"):
            warnings.append("recommend a police report for suspected fraud over $500")

        tier = tiers.get(account_id)
        limit = LIMITS.get(tier)
        if limit is None:
            errors.append("valid account tier is required to check open-dispute limit")
        current = existing.get(account_id)
        if not isinstance(current, int) or isinstance(current, bool) or current < 0:
            errors.append("nonnegative open dispute count is required for this account")
        elif limit is not None and current + accepted_per_account.get(account_id, 0) >= limit:
            errors.append("account open-dispute limit would be exceeded")

        pc_reasons = []
        if category not in PC_CATEGORIES:
            pc_reasons.append("category is not required for provisional credit")
        if not claim.get("reported_within_60_days_of_statement"):
            pc_reasons.append("timely statement reporting is not evidenced")
        if not claim.get("written_statement_provided"):
            pc_reasons.append("written statement is not provided")
        if not claim.get("account_open") or claim.get("account_has_holds_or_restrictions"):
            pc_reasons.append("account is not confirmed OPEN without holds/restrictions")
        if category not in {"card_present_fraud", "card_not_present_fraud"} and not claim.get("contacted_merchant"):
            pc_reasons.append("merchant was not contacted for non-fraud claim")
        if claim.get("pin_compromised") == "yes_shared":
            pc_reasons.append("PIN was voluntarily shared")
        age_days = claim.get("account_age_days")
        if not isinstance(age_days, int) or isinstance(age_days, bool) or age_days < 0:
            pc_reasons.append("account_age_days is not established")
        elif category == "card_not_present_fraud" and age_days < 30:
            pc_reasons.append("card-not-present claim is on an account under 30 days old")
        provisional = not pc_reasons
        action = ACTIONS.get(category)
        fileable = not errors
        if fileable:
            accepted_per_account[account_id] = accepted_per_account.get(account_id, 0) + 1
            if card_id and action and (card_id not in by_card or SEVERITY[action] > SEVERITY[by_card[card_id]]):
                by_card[card_id] = action
        results.append({
            "index": index, "fileable": fileable, "errors": errors, "warnings": warnings,
            "card_action_metadata": action,
            "provisional_credit_eligible": provisional,
            "provisional_credit_reasons_not_required_or_unconfirmed": pc_reasons,
        })
    return {"valid_input": not top_errors, "input_errors": top_errors, "disputes": results,
            "card_actions_after_successful_filings": by_card}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid_input": False, "input_errors": [str(exc)], "disputes": [], "card_actions_after_successful_filings": {}}))
        sys.exit(2)
