#!/usr/bin/env python3
"""Validate gathered debit-dispute facts and calculate deterministic recommendations.

Input JSON:
{
  "account": {"status": "OPEN", "age_days": 0,
              "has_holds_or_restrictions": false},
  "disputes": [{"card_id": str, "category": str,
    "transaction_type": str, "disputed_amount": number,
    "transaction_amount": number, "within_60_days": bool,
    "timely_statement_report": bool, "written_statement_provided": bool,
    "contacted_merchant": bool, "pin_compromised": str}]
}

Output JSON has one assessment per supplied dispute and a most-severe action per card.
This helper makes no banking calls and does not replace account, identity, transaction,
or open-dispute-limit verification.
"""
import json
import sys

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
PROVISIONAL_CATEGORIES = FRAUD | {
    "unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"
}
NON_REQUIRED_CATEGORIES = {
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "atm_deposit_not_credited", "incorrect_amount",
}
ACTION = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def as_bool(value):
    return isinstance(value, bool)


def assess(item, account):
    errors = []
    category = item.get("category")
    if category not in CATEGORIES:
        errors.append("category must be an allowed dispute category")
    if item.get("transaction_type") not in TYPES:
        errors.append("transaction_type must be an allowed transaction type")
    if item.get("pin_compromised") not in PINS:
        errors.append("pin_compromised must be yes_shared, yes_observed, no, or unknown")
    for key in ("within_60_days", "timely_statement_report", "written_statement_provided", "contacted_merchant"):
        if not as_bool(item.get(key)):
            errors.append(f"{key} must be boolean")
    amount = item.get("disputed_amount")
    transaction_amount = item.get("transaction_amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        errors.append("disputed_amount must be a number of at least 1.00")
    if not isinstance(transaction_amount, (int, float)) or isinstance(transaction_amount, bool) or transaction_amount <= 0:
        errors.append("transaction_amount must be a positive number")
    elif isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount > transaction_amount:
        errors.append("disputed_amount cannot exceed transaction_amount")
    if not item.get("card_id"):
        errors.append("card_id is required for per-card action planning")
    if account.get("status") != "OPEN":
        errors.append("linked checking account must be OPEN")
    if account.get("has_holds_or_restrictions") is not False:
        errors.append("account must have no holds or restrictions")
    if category not in FRAUD and category in CATEGORIES and item.get("contacted_merchant") is not True:
        errors.append("merchant contact is required before a non-fraud dispute")

    action = ACTION.get(category, "keep_active")
    exclusions = []
    if category in NON_REQUIRED_CATEGORIES:
        exclusions.append("category is not provisionally-credit-required")
    if category not in FRAUD and item.get("contacted_merchant") is not True:
        exclusions.append("merchant has not been contacted for non-fraud dispute")
    if item.get("pin_compromised") == "yes_shared":
        exclusions.append("PIN was voluntarily shared")
    age = account.get("age_days")
    if category == "card_not_present_fraud" and isinstance(age, (int, float)) and not isinstance(age, bool) and age < 30:
        exclusions.append("new account card-not-present exclusion")
    prerequisites = (
        item.get("timely_statement_report") is True
        and category in PROVISIONAL_CATEGORIES
        and item.get("written_statement_provided") is True
        and account.get("status") == "OPEN"
        and account.get("has_holds_or_restrictions") is False
    )
    required = bool(prerequisites and not exclusions)
    affidavit = bool(category == "atm_cash_discrepancy" and isinstance(amount, (int, float))
                     and not isinstance(amount, bool) and amount > 200)
    return {
        "card_id": item.get("card_id"),
        "category": category,
        "valid": not errors,
        "errors": errors,
        "card_action": action,
        "provisional_credit_required": required,
        "provisional_credit_exclusions": exclusions,
        "third_party_atm_affidavit_required_if_third_party": affidavit,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "error": f"invalid JSON: {exc.msg}"}))
        return
    account = payload.get("account")
    disputes = payload.get("disputes")
    if not isinstance(account, dict) or not isinstance(disputes, list):
        print(json.dumps({"valid": False, "error": "account object and disputes array are required"}))
        return
    assessments = [assess(item, account) if isinstance(item, dict) else {
        "valid": False, "errors": ["each dispute must be an object"], "card_id": None
    } for item in disputes]
    per_card = {}
    for result in assessments:
        card = result.get("card_id")
        if card:
            prior = per_card.get(card, "keep_active")
            if SEVERITY.get(result.get("card_action"), 0) > SEVERITY[prior]:
                per_card[card] = result["card_action"]
            else:
                per_card.setdefault(card, prior)
    print(json.dumps({
        "valid": all(x.get("valid") for x in assessments),
        "assessments": assessments,
        "actual_card_action_by_card": per_card,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
