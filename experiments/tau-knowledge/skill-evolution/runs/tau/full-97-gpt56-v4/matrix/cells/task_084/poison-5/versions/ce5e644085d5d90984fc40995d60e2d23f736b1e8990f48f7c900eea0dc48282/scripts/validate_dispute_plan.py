#!/usr/bin/env python3
"""Validate normalized debit-dispute plan JSON from stdin; emit JSON to stdout."""
import json
import sys

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
CREDIT_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}

def action_for(category):
    return ACTIONS.get(category, "keep_active")

def main(data):
    account = data.get("account") or {}
    claims = data.get("claims") or []
    common = []
    if not data.get("identity_verified"):
        common.append("identity_verified must be true after logged two-factor verification")
    if account.get("status") != "OPEN":
        common.append("checking account must be OPEN")
    if account.get("has_holds_or_restrictions") is not False:
        common.append("account standing must explicitly show no holds or restrictions")
    tier = str(account.get("account_class", "")).strip().lower().replace(" tier", "")
    if tier not in LIMITS:
        common.append("account_class must be Entry, Mid, Premium, or Elite")
    count = account.get("open_dispute_count")
    if not isinstance(count, int) or count < 0:
        common.append("open_dispute_count must be a non-negative integer")
    results = []
    for index, claim in enumerate(claims):
        errors = list(common)
        category = claim.get("category")
        amount = claim.get("amount")
        if not claim.get("transaction_id"):
            errors.append("transaction_id is required from transaction-history matching")
        if category not in CATEGORIES:
            errors.append("unsupported dispute category")
        if claim.get("transaction_type") not in TYPES:
            errors.append("unsupported or missing transaction_type")
        if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
            errors.append("amount must be at least $1.00")
        age = claim.get("transaction_age_days")
        if not isinstance(age, (int, float)) or age < 0 or age > 60:
            errors.append("transaction must be 0 through 60 days old")
        if claim.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown"}:
            errors.append("pin_compromised is missing or invalid")
        if not isinstance(claim.get("contacted_merchant"), bool):
            errors.append("contacted_merchant must be boolean")
        if not isinstance(claim.get("written_statement_provided"), bool):
            errors.append("written_statement_provided must be boolean")
        if tier in LIMITS and isinstance(count, int) and count + index >= LIMITS[tier]:
            errors.append("filing would exceed this account tier's open-dispute limit")
        timely = claim.get("timely_statement_reporting") is True
        eligible = (category in CREDIT_CATEGORIES and timely and
                    claim.get("written_statement_provided") is True and
                    account.get("status") == "OPEN" and
                    account.get("has_holds_or_restrictions") is False)
        if category not in CREDIT_CATEGORIES:
            eligible = False
        if category not in {"card_present_fraud", "card_not_present_fraud"} and not claim.get("contacted_merchant", False):
            eligible = False
        if claim.get("pin_compromised") == "yes_shared":
            eligible = False
        if category == "card_not_present_fraud" and isinstance(claim.get("account_age_days"), (int, float)) and claim["account_age_days"] < 30:
            eligible = False
        results.append({"index": index, "valid": not errors, "errors": errors,
                        "provisional_credit_eligible": eligible,
                        "card_action": action_for(category)})
    return {"valid": bool(claims) and all(x["valid"] for x in results), "claims": results}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        sys.exit(1)
