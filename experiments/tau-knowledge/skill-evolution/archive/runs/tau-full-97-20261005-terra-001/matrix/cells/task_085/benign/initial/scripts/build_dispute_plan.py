#!/usr/bin/env python3
"""Validate and assemble a debit-card ATM dispute filing plan.

Reads a JSON case object on stdin and writes a JSON result on stdout.  This
program neither calls banking tools nor changes account or card state.
"""
import json
import sys
from datetime import datetime

DATE_FMT = "%m/%d/%Y"
OPEN_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
ACTION_BY_CATEGORY = {
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
QUALIFYING_PROVISIONAL = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
LIABILITY_CAP = {
    "within_2_business_days": 50.0,
    "within_60_days": 500.0,
    "after_60_days": None,
}


def val(mapping, key, errors, label=None):
    if key not in mapping:
        errors.append("Missing " + (label or key) + ".")
        return None
    return mapping[key]


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None


def tier_key(value):
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    for tier in LIMITS:
        if tier in text:
            return tier
    return None


def is_bool(value):
    return isinstance(value, bool)


def main(data):
    errors, warnings = [], []
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    tx = data.get("transaction") if isinstance(data.get("transaction"), dict) else {}
    case = data.get("case") if isinstance(data.get("case"), dict) else {}
    atm = data.get("atm") if isinstance(data.get("atm"), dict) else {}

    today = parse_date(val(data, "today", errors), "today", errors)
    tx_date = parse_date(val(tx, "date", errors, "transaction.date"), "transaction.date", errors)
    discovery_date = parse_date(val(case, "discovery_date", errors), "case.discovery_date", errors)
    opened = parse_date(val(account, "date_opened", errors, "account.date_opened"), "account.date_opened", errors)

    if data.get("verified") is not True:
        errors.append("Customer identity must be verified and logged before filing.")

    account_id = val(account, "account_id", errors, "account.account_id")
    card_account_id = val(card, "account_id", errors, "card.account_id")
    tx_account_id = val(tx, "account_id", errors, "transaction.account_id")
    if account.get("account_type", "").lower() != "checking":
        errors.append("The linked account must be a checking account.")
    if account.get("status") != "OPEN":
        errors.append("The linked checking account must be OPEN.")
    if not account_id or card_account_id != account_id or tx_account_id != account_id:
        errors.append("Card, transaction, and selected checking account must have the same account_id.")
    for field in ("card_id", "user_id"):
        if not card.get(field):
            errors.append(f"Missing card.{field}.")
    if not tx.get("transaction_id"):
        errors.append("Missing transaction.transaction_id.")

    try:
        transaction_amount = abs(float(val(tx, "amount", errors, "transaction.amount")))
        disputed_amount = float(val(case, "disputed_amount", errors))
        if transaction_amount < 1:
            errors.append("The transaction must be at least $1.00.")
        if disputed_amount < 1:
            errors.append("The disputed amount must be at least $1.00.")
        if disputed_amount > transaction_amount:
            errors.append("The disputed amount cannot exceed the transaction amount.")
    except (TypeError, ValueError):
        transaction_amount, disputed_amount = 0.0, 0.0
        errors.append("Transaction and disputed amounts must be numeric.")

    if today and tx_date:
        age = (today - tx_date).days
        if age < 0:
            errors.append("Transaction date cannot be after filing date.")
        elif age > 60:
            errors.append("Transaction is more than 60 days old and cannot be filed through this workflow.")
    if tx_date and discovery_date and discovery_date < tx_date:
        errors.append("Discovery date cannot precede transaction date.")

    tier = tier_key(account.get("account_class"))
    if not tier:
        errors.append("Account class must resolve to Entry, Mid, Premium, or Elite tier.")
        limit = None
    else:
        limit = LIMITS[tier]
    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        errors.append("disputes must be a list of dispute records.")
        disputes = []
    open_count = sum(
        1 for d in disputes if isinstance(d, dict) and d.get("account_id") == account_id
        and str(d.get("status", "")).upper() in OPEN_STATUSES
    )
    if limit is not None and open_count >= limit:
        errors.append(f"Open-dispute limit reached for this account ({open_count}/{limit}).")

    category = val(case, "category", errors)
    tx_type = val(case, "transaction_type", errors)
    if category not in CATEGORIES:
        errors.append("case.category is not an allowed dispute category.")
    if tx_type not in TRANSACTION_TYPES:
        errors.append("case.transaction_type is not an allowed transaction type.")
    if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal":
        errors.append("ATM cash discrepancy must use transaction_type atm_withdrawal.")
    if category == "atm_deposit_not_credited" and tx_type != "atm_deposit":
        errors.append("ATM deposit not credited must use transaction_type atm_deposit.")

    required_case_bools = [
        "card_in_possession", "contacted_merchant", "police_report_filed",
        "written_statement_provided", "reported_within_60_days_of_statement",
    ]
    for field in required_case_bools:
        if not is_bool(case.get(field)):
            errors.append(f"case.{field} must be boolean.")
    if case.get("pin_compromised") not in PIN_VALUES:
        errors.append("case.pin_compromised must be yes_shared, yes_observed, no, or unknown.")
    if not is_bool(atm.get("rho_bank_owned")):
        errors.append("atm.rho_bank_owned must be boolean.")

    # Account restrictions are material to provisional-credit eligibility.
    if not is_bool(account.get("holds_or_restrictions")):
        errors.append("account.holds_or_restrictions must be boolean.")

    timely = case.get("reported_within_60_days_of_statement") is True
    account_clear = account.get("status") == "OPEN" and account.get("holds_or_restrictions") is False
    written = case.get("written_statement_provided") is True
    category_qualifies = category in QUALIFYING_PROVISIONAL
    voluntary_pin = case.get("pin_compromised") == "yes_shared"
    merchant_contact_missing = category not in {"card_present_fraud", "card_not_present_fraud"} and case.get("contacted_merchant") is False
    provisional = bool(timely and account_clear and written and category_qualifies and not voluntary_pin and not merchant_contact_missing)

    if not timely:
        warnings.append("Provisional credit is not required because timely reporting within 60 days of the statement is not established.")
    if not written:
        warnings.append("Written statement is absent; provisional credit is not required.")
    if merchant_contact_missing:
        warnings.append("Customer has not contacted the merchant/ATM owner; provisional credit is not required for this non-fraud case.")
    if voluntary_pin:
        warnings.append("Customer reported voluntarily sharing the PIN; provisional credit is not required.")
    if category not in QUALIFYING_PROVISIONAL:
        warnings.append("This category is not one for which provisional credit is required.")
    if category == "atm_cash_discrepancy" and disputed_amount > 200:
        warnings.append("ATM cash discrepancy exceeds $200: provide the Electronic Fund Transfer Error Resolution Affidavit notice.")
    if atm.get("rho_bank_owned") is False:
        warnings.append("Third-party ATM: submit to the network/owner; investigation may take up to 90 days.")
    if atm.get("rho_bank_owned") is True and atm.get("journal_confirmed_discrepancy") is True:
        warnings.append("Rho-Bank journal confirms discrepancy: arrange immediate provisional credit after filing.")
    elif atm.get("rho_bank_owned") is True and atm.get("journal_confirmed_discrepancy") is False:
        warnings.append("Journal shows requested amount; explain it does not validate the claim, while preserving formal-dispute availability.")
    elif atm.get("rho_bank_owned") is True:
        warnings.append("Review the Rho-Bank ATM journal/related transaction before representing that a discrepancy is confirmed.")

    action = ACTION_BY_CATEGORY.get(category)
    eligible_to_file = not errors
    result = {
        "eligible_to_file": eligible_to_file,
        "errors": errors,
        "warnings": warnings,
        "open_dispute_count": open_count,
        "open_dispute_limit": limit,
        "card_action": action,
        "provisional_credit_eligible": provisional,
    }

    if provisional:
        # Rho-confirmed shortages are immediate; otherwise use documented timing.
        if atm.get("rho_bank_owned") and atm.get("journal_confirmed_discrepancy") is True:
            result["provisional_credit_timing"] = "immediate"
        elif today and opened and (today - opened).days < 30:
            result["provisional_credit_timing"] = "within_20_business_days_of_filing"
        else:
            result["provisional_credit_timing"] = "within_10_business_days_of_filing"
        liability = case.get("liability_tier")
        if liability in LIABILITY_CAP:
            cap = LIABILITY_CAP[liability]
            if cap is None:
                result["provisional_credit_amount_recommendation"] = 0.0
                warnings.append("Late-reporting tier can make funds unrecoverable; obtain operational review before promising credit.")
            else:
                result["provisional_credit_amount_recommendation"] = round(max(0.0, disputed_amount - min(disputed_amount, cap)), 2)

    if eligible_to_file:
        result["file_args"] = {
            "transaction_id": tx["transaction_id"],
            "account_id": account_id,
            "card_id": card["card_id"],
            "user_id": card["user_id"],
            "dispute_category": category,
            "transaction_date": tx["date"],
            "discovery_date": case["discovery_date"],
            "disputed_amount": disputed_amount,
            "transaction_type": tx_type,
            "card_in_possession": case["card_in_possession"],
            "pin_compromised": case["pin_compromised"],
            "contacted_merchant": case["contacted_merchant"],
            "police_report_filed": case["police_report_filed"],
            "written_statement_provided": case["written_statement_provided"],
            "provisional_credit_eligible": provisional,
            "card_action": action,
        }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible_to_file": False, "errors": [str(exc)], "warnings": []}, sort_keys=True))
