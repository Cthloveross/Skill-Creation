#!/usr/bin/env python3
"""Validate a normalized debit-card dispute plan.

Read one JSON object from stdin and write exactly one JSON object to stdout.
This is a rules/planning helper only; it performs no bank lookup or bank action.
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
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
                 "atm_cash_discrepancy", "duplicate_charge"}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}
LIABILITY_TIMINGS = {"within_2_business_days", "within_60_days", "after_60_days", "not_applicable"}


def parse_date(value):
    return datetime.strptime(str(value), "%m/%d/%Y").date()


def as_nonnegative_int(value):
    result = int(value)
    if result < 0:
        raise ValueError("must not be negative")
    return result


def normalized_tier(data):
    # account_tier is preferred because the account lookup's account class can
    # mean account type in some runtimes. account_class is retained for callers
    # whose lookup returns Entry/Mid/Premium/Elite directly.
    raw = data.get("account_tier", data.get("account_class", ""))
    return str(raw).strip().lower().replace(" tier", "")


def liability_amount(amount, category, timing):
    """Return required filing value, or None when the timing is unavailable."""
    if category not in {"unauthorized_transaction", *FRAUD_CATEGORIES}:
        return 0.0
    if timing == "within_2_business_days":
        return min(amount, 50.0)
    if timing == "within_60_days":
        return min(amount, 500.0)
    if timing == "after_60_days":
        return -1.0
    return None


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON value must be an object")
    except Exception as exc:
        print(json.dumps({"eligible_to_file": False, "blockers": ["invalid_json: " + str(exc)]}, sort_keys=True))
        return

    blockers, warnings = [], []
    required = ["current_date", "transaction_date", "amount", "account_type", "account_status",
                "account_class", "card_linked", "verification_logged", "open_dispute_count",
                "category", "transaction_type", "written_statement_provided",
                "timely_statement_report", "account_restricted", "contacted_merchant",
                "pin_compromised", "account_age_days"]
    missing = [key for key in required if key not in data]
    if missing:
        print(json.dumps({"eligible_to_file": False, "blockers": ["missing fields: " + ", ".join(missing)]}, sort_keys=True))
        return

    try:
        age = (parse_date(data["current_date"]) - parse_date(data["transaction_date"])).days
    except Exception:
        blockers.append("dates must use MM/DD/YYYY and form a valid interval")
        age = None
    try:
        amount = float(data["amount"])
        if amount < 1:
            blockers.append("transaction amount is below $1.00")
    except (TypeError, ValueError):
        amount = None
        blockers.append("amount must be numeric")

    category = data["category"]
    if not data["verification_logged"]:
        blockers.append("customer verification has not been logged")
    if str(data["account_type"]).lower() != "checking":
        blockers.append("debit card dispute requires a checking account")
    if str(data["account_status"]).upper() != "OPEN":
        blockers.append("checking account is not OPEN")
    if not data["card_linked"]:
        blockers.append("debit card is not linked to the selected checking account")
    if age is not None and (age < 0 or age > 60):
        blockers.append("transaction is not within 60 days")
    if category not in CATEGORIES:
        blockers.append("invalid dispute category")
    if data["transaction_type"] not in TYPES:
        blockers.append("invalid transaction type")

    try:
        open_count = as_nonnegative_int(data["open_dispute_count"])
    except (TypeError, ValueError):
        open_count = None
        blockers.append("open_dispute_count must be a nonnegative integer")
    tier = normalized_tier(data)
    limit = LIMITS.get(tier)
    if limit is None:
        # A known tier is best. If only an unfamiliar product label is returned,
        # Entry's limit is a safe lower bound; at two existing disputes, stop
        # rather than assuming the product's tier.
        if open_count is not None and open_count >= LIMITS["entry"]:
            blockers.append("account tier is not established and may be at its open-dispute limit")
        else:
            warnings.append("account tier is not established; Entry Tier's limit of 2 was used as a safe lower bound")
    elif open_count is not None and open_count >= limit:
        blockers.append("account has reached its open-dispute limit")

    if category == "duplicate_charge" and data.get("duplicate_rank") not in (None, 1):
        blockers.append("select the earliest duplicate transaction first")
    if category in FRAUD_CATEGORIES and data.get("fraud_suspected") is False:
        blockers.append("fraud category conflicts with fraud_suspected=false")
    if category == "unauthorized_transaction" and data.get("fraud_suspected") is True:
        blockers.append("suspected fraud must use a card-present or card-not-present fraud category")

    merchant_categories = {"duplicate_charge", "incorrect_amount", "goods_services_not_received", "recurring_charge_after_cancellation"}
    if category in merchant_categories and not data["contacted_merchant"]:
        warnings.append("merchant has not been contacted; filing may proceed but provisional credit is not required")
    try:
        account_age_days = as_nonnegative_int(data["account_age_days"])
    except (TypeError, ValueError):
        account_age_days = None
        blockers.append("account_age_days must be a nonnegative integer")

    pc_required = (
        category in PC_CATEGORIES and bool(data["timely_statement_report"])
        and bool(data["written_statement_provided"])
        and str(data["account_status"]).upper() == "OPEN"
        and not bool(data["account_restricted"])
        and data["pin_compromised"] != "yes_shared"
        and not (category == "card_not_present_fraud" and account_age_days is not None and account_age_days < 30)
        and not (category in merchant_categories and not data["contacted_merchant"])
    )
    timing = data.get("liability_timing", "not_applicable")
    if timing not in LIABILITY_TIMINGS:
        blockers.append("liability_timing is invalid")
        customer_max_liability_amount = None
    elif amount is None:
        customer_max_liability_amount = None
    else:
        customer_max_liability_amount = liability_amount(amount, category, timing)
        if customer_max_liability_amount is None:
            blockers.append("liability timing is required for an unauthorized or fraud dispute")

    print(json.dumps({
        "eligible_to_file": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "transaction_age_days": age,
        "card_action": ACTIONS.get(category, "keep_active"),
        "provisional_credit_required": pc_required,
        "customer_max_liability_amount": customer_max_liability_amount,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
