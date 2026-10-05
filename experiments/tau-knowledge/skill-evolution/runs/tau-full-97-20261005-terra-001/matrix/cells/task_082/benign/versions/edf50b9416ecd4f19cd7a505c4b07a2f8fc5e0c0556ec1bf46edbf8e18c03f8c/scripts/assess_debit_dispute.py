#!/usr/bin/env python3
"""Validate structured debit-card dispute intake facts without taking bank action.

Input JSON schema:
{
  "category": one accepted filing category,
  "transaction_date": "MM/DD/YYYY", "current_date": "MM/DD/YYYY" (optional),
  "disputed_amount": number, "account_status": "OPEN",
  "account_has_hold_or_restriction": bool, "card_linked_to_account": bool,
  "account_tier": "Entry Tier"|"Mid Tier"|"Premium Tier"|"Elite Tier",
  "open_disputes_for_account": integer,
  "reported_within_60_days_of_statement": bool,
  "written_statement_provided": bool, "contacted_merchant": bool,
  "pin_compromised": "yes_shared"|"yes_observed"|"no"|"unknown",
  "account_age_days": integer (optional),
  "international_or_non_us_pos": bool (optional)
}

The output is advisory. The caller must still ensure verified identity, valid IDs,
transaction ownership, required filing fields, and applicable ATM handling.
"""
import datetime as dt
import json
import sys

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud"
}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge"
}
TIERS = {"Entry Tier": 2, "Mid Tier": 3, "Premium Tier": 4, "Elite Tier": 5}
NON_FRAUD = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation"
}


def parse_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(field + " must use MM/DD/YYYY format")
        return None
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(field + " must use MM/DD/YYYY format")
        return None


def main(d):
    errors, warnings = [], []
    category = d.get("category")
    if category not in CATEGORIES:
        errors.append("category must be one of the supported debit-dispute categories")
    amount = d.get("disputed_amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 1:
        errors.append("disputed_amount must be at least 1.00")
    if d.get("account_status") != "OPEN":
        errors.append("the debit card must be linked to an OPEN checking account")
    if d.get("card_linked_to_account") is not True:
        errors.append("confirm that the debit card is linked to the checking account")

    tier = d.get("account_tier")
    count = d.get("open_disputes_for_account")
    if tier not in TIERS:
        warnings.append("account_tier is required to check the per-account open-dispute limit")
    elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
        warnings.append("open_disputes_for_account is required to check the per-account limit")
    elif count >= TIERS[tier]:
        errors.append("open-dispute limit reached for this checking account tier")

    tx_date = parse_date(d.get("transaction_date"), "transaction_date", errors)
    now = parse_date(d.get("current_date"), "current_date", errors)
    if tx_date is None:
        warnings.append("transaction_date is required to confirm the 60-day filing requirement")
    elif now is None:
        warnings.append("current_date was not supplied; confirm the transaction is no more than 60 days old")
    elif (now - tx_date).days > 60:
        errors.append("transaction is more than 60 days old")
    elif (now - tx_date).days < 0:
        errors.append("transaction_date cannot be in the future")

    required_fields = ["discovery_date", "transaction_type", "card_in_possession", "pin_compromised", "contacted_merchant", "police_report_filed", "written_statement_provided"]
    missing = [key for key in required_fields if key not in d]
    if missing:
        warnings.append("filing still needs: " + ", ".join(missing))
    if "discovery_date" in d:
        parse_date(d.get("discovery_date"), "discovery_date", errors)
    if d.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown", None}:
        errors.append("pin_compromised has an unsupported value")

    action = ACTIONS.get(category, "keep_active" if category in CATEGORIES else None)
    timely = d.get("reported_within_60_days_of_statement") is True
    written = d.get("written_statement_provided") is True
    open_unrestricted = d.get("account_status") == "OPEN" and d.get("account_has_hold_or_restriction") is not True
    nonfraud_merchant_issue = category in NON_FRAUD and category not in {"unauthorized_transaction"} and d.get("contacted_merchant") is not True
    pin_shared = d.get("pin_compromised") == "yes_shared"
    new_cnp = category == "card_not_present_fraud" and isinstance(d.get("account_age_days"), int) and d["account_age_days"] < 30
    provisional = bool(category in PC_CATEGORIES and timely and written and open_unrestricted and not nonfraud_merchant_issue and not pin_shared and not new_cnp)

    if "reported_within_60_days_of_statement" not in d:
        warnings.append("confirm whether report was within 60 days of the statement date")
    if d.get("account_has_hold_or_restriction") is None:
        warnings.append("confirm the OPEN account has no hold or restriction for provisional-credit assessment")
    if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
        warnings.append("determine whether the ATM was Rho-Bank or third-party")
    if category == "duplicate_charge":
        warnings.append("when duplicates exist, dispute the earliest transaction")
    if category == "recurring_charge_after_cancellation":
        warnings.append("a recurring block for future charges is separate and blocks all recurring payments on the card")

    age = d.get("account_age_days")
    issuance = 20 if isinstance(age, int) and age < 30 else 10
    extended = d.get("international_or_non_us_pos") is True or (isinstance(age, int) and age < 30)
    investigation = 90 if extended else 45
    return {
        "valid_to_file": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "card_action": action,
        "provisional_credit_eligible": provisional,
        "provisional_credit_issuance_business_days": issuance if provisional else None,
        "investigation_timeline_business_days_if_provisional_credit": investigation if provisional else None,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
