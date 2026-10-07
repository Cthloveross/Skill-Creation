#!/usr/bin/env python3
"""Validate a normalized debit-card-dispute plan from JSON stdin; emit JSON stdout.
This helper is advisory only: it does not retrieve records or make banking changes.
"""
import json
import sys

CATEGORIES = {"unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount", "goods_services_not_received", "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud"}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
CREDIT_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}

def card_action(category):
    if category in FRAUD:
        return "close_and_reissue"
    if category == "unauthorized_transaction":
        return "freeze_pending_investigation"
    return "keep_active"

def limit_for(account):
    explicit = account.get("max_open_disputes")
    if isinstance(explicit, int) and explicit >= 0:
        return explicit
    tier = str(account.get("tier", account.get("account_class", ""))).strip().lower().replace(" tier", "")
    # An unlabelled account must not be assumed to have a more generous cap.
    # Entry's cap is the safe fallback until a tier is obtained.
    return LIMITS.get(tier, 2)

def main(data):
    account = data.get("account") or {}
    claims = data.get("claims") or []
    common = []
    if data.get("identity_verified") is not True:
        common.append("identity_verified must be true after two-field verification is logged")
    if account.get("status") != "OPEN":
        common.append("checking account must be OPEN")
    count = account.get("open_dispute_count")
    if not isinstance(count, int) or count < 0:
        common.append("open_dispute_count must be a non-negative integer")
    cap = limit_for(account)
    results = []
    for index, claim in enumerate(claims):
        errors = list(common)
        category = claim.get("category")
        amount = claim.get("amount")
        if not claim.get("transaction_id"):
            errors.append("transaction_id is required from transaction matching")
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
        if not isinstance(claim.get("card_in_possession"), bool):
            errors.append("card_in_possession must be boolean")
        if not isinstance(claim.get("contacted_merchant"), bool):
            errors.append("contacted_merchant must be boolean")
        if not isinstance(claim.get("police_report_filed"), bool):
            errors.append("police_report_filed must be boolean")
        if not isinstance(claim.get("written_statement_provided"), bool):
            errors.append("written_statement_provided must be boolean")
        if cap is not None and isinstance(count, int) and count + index >= cap:
            errors.append("filing would exceed this account's open-dispute cap")
        # A positive hold/restriction blocks eligibility. Some account lookups do
        # not expose this field, so absence is not treated as a reported hold.
        no_restriction = account.get("has_holds_or_restrictions") is not True
        eligible = (category in CREDIT_CATEGORIES and claim.get("timely_statement_reporting") is True and claim.get("written_statement_provided") is True and account.get("status") == "OPEN" and no_restriction)
        if category not in FRAUD and claim.get("contacted_merchant") is not True:
            eligible = False
        if claim.get("pin_compromised") == "yes_shared":
            eligible = False
        if category == "card_not_present_fraud" and isinstance(claim.get("account_age_days"), (int, float)) and claim["account_age_days"] < 30:
            eligible = False
        results.append({"index": index, "valid": not errors, "errors": errors, "provisional_credit_eligible": eligible, "card_action": card_action(category)})
    return {"valid": bool(claims) and all(row["valid"] for row in results), "claims": results}

if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        sys.exit(1)
