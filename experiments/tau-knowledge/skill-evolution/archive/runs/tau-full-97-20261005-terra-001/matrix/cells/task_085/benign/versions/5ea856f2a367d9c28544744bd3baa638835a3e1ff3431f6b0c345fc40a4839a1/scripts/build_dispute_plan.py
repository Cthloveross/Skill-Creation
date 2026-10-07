#!/usr/bin/env python3
"""Build a validated debit-card ATM dispute filing plan.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
helper is deterministic and does not invoke banking tools or change any state.
"""
import json
import sys
from datetime import datetime

DATE_FMT = "%m/%d/%Y"
OPEN_DISPUTE_STATUSES = {
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
PROVISIONAL_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}


def required(mapping, key, errors, label=None):
    if key not in mapping:
        errors.append("Missing " + (label or key) + ".")
        return None
    return mapping[key]


def date_value(value, label, errors, needed=True):
    if value is None and not needed:
        return None
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None


def as_tier(value):
    normalized = str(value or "").lower().replace("_", " ").replace("-", " ")
    for tier in LIMITS:
        if tier in normalized:
            return tier
    return None


def is_bool(value):
    return isinstance(value, bool)


def main(data):
    errors, warnings = [], []
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    transaction = data.get("transaction") if isinstance(data.get("transaction"), dict) else {}
    case = data.get("case") if isinstance(data.get("case"), dict) else {}
    atm = data.get("atm") if isinstance(data.get("atm"), dict) else {}

    today = date_value(required(data, "today", errors), "today", errors)
    transaction_date_text = required(transaction, "date", errors, "transaction.date")
    transaction_date = date_value(transaction_date_text, "transaction.date", errors)
    discovery_text = required(case, "discovery_date", errors, "case.discovery_date")
    discovery_date = date_value(discovery_text, "case.discovery_date", errors)

    if data.get("verified") is not True:
        errors.append("Customer identity must be verified and logged before filing.")

    account_id = required(account, "account_id", errors, "account.account_id")
    card_account_id = required(card, "account_id", errors, "card.account_id")
    transaction_account_id = required(transaction, "account_id", errors, "transaction.account_id")
    if str(account.get("account_type", "")).lower() != "checking":
        errors.append("The linked account must be a checking account.")
    if account.get("status") != "OPEN":
        errors.append("The linked checking account must be OPEN.")
    if not account_id or card_account_id != account_id or transaction_account_id != account_id:
        errors.append("Card, transaction, and selected checking account must have the same account_id.")
    if not card.get("card_id"):
        errors.append("Missing card.card_id.")
    if not card.get("user_id"):
        errors.append("Missing card.user_id.")
    if not transaction.get("transaction_id"):
        errors.append("Missing transaction.transaction_id.")

    try:
        transaction_amount = abs(float(required(transaction, "amount", errors, "transaction.amount")))
        disputed_amount = float(required(case, "disputed_amount", errors, "case.disputed_amount"))
        if transaction_amount < 1:
            errors.append("The transaction must be at least $1.00.")
        if disputed_amount < 1:
            errors.append("The disputed amount must be at least $1.00.")
        if disputed_amount > transaction_amount:
            errors.append("The disputed amount cannot exceed the transaction amount.")
    except (TypeError, ValueError):
        disputed_amount = 0.0
        errors.append("Transaction and disputed amounts must be numeric.")

    if today and transaction_date:
        age = (today - transaction_date).days
        if age < 0:
            errors.append("Transaction date cannot be after filing date.")
        elif age > 60:
            errors.append("Transaction is more than 60 days old and cannot be filed through this workflow.")
    if transaction_date and discovery_date and discovery_date < transaction_date:
        errors.append("Discovery date cannot precede transaction date.")

    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        errors.append("disputes must be a list of dispute records.")
        disputes = []
    open_count = sum(
        1 for dispute in disputes
        if isinstance(dispute, dict)
        and dispute.get("account_id") == account_id
        and str(dispute.get("status", "")).upper() in OPEN_DISPUTE_STATUSES
    )
    tier = as_tier(account.get("account_class"))
    if tier:
        limit = LIMITS[tier]
        if open_count >= limit:
            errors.append(f"Open-dispute limit reached for this account ({open_count}/{limit}).")
    else:
        # Entry's limit is the strictest.  Below it, capacity is provable even
        # when an account response omitted its class.
        limit = LIMITS["entry"]
        if open_count >= limit:
            errors.append("Account tier is required to establish remaining dispute capacity.")
        else:
            warnings.append("Account tier was not exposed; capacity is established using the Entry-tier limit.")

    category = required(case, "category", errors, "case.category")
    transaction_type = required(case, "transaction_type", errors, "case.transaction_type")
    if category not in CATEGORIES:
        errors.append("case.category is not an allowed dispute category.")
    if transaction_type not in TRANSACTION_TYPES:
        errors.append("case.transaction_type is not an allowed transaction type.")
    if category == "atm_cash_discrepancy" and transaction_type != "atm_withdrawal":
        errors.append("ATM cash discrepancy must use transaction_type atm_withdrawal.")
    if category == "atm_deposit_not_credited" and transaction_type != "atm_deposit":
        errors.append("ATM deposit not credited must use transaction_type atm_deposit.")
    if transaction.get("type") and transaction_type != transaction.get("type"):
        errors.append("case.transaction_type must match transaction.type.")

    for field in ("card_in_possession", "contacted_merchant", "written_statement_provided"):
        if not is_bool(case.get(field)):
            errors.append(f"case.{field} must be boolean.")
    if case.get("pin_compromised") not in PIN_VALUES:
        errors.append("case.pin_compromised must be yes_shared, yes_observed, no, or unknown.")
    if not is_bool(atm.get("rho_bank_owned")):
        errors.append("atm.rho_bank_owned must be boolean.")
    if "police_report_filed" in case and not is_bool(case["police_report_filed"]):
        errors.append("case.police_report_filed must be boolean when supplied.")
    if "reported_within_60_days_of_statement" in case and not is_bool(case["reported_within_60_days_of_statement"]):
        errors.append("case.reported_within_60_days_of_statement must be boolean when supplied.")

    holds = account.get("holds_or_restrictions")
    if holds is not None and not is_bool(holds):
        errors.append("account.holds_or_restrictions must be boolean or null when supplied.")

    timely_statement = case.get("reported_within_60_days_of_statement") is True
    account_clear = account.get("status") == "OPEN" and holds is False
    written = case.get("written_statement_provided") is True
    qualifying_category = category in PROVISIONAL_CATEGORIES
    voluntary_pin = case.get("pin_compromised") == "yes_shared"
    nonfraud = category not in {"card_present_fraud", "card_not_present_fraud"}
    no_merchant_contact = nonfraud and case.get("contacted_merchant") is False
    provisional = bool(
        timely_statement and account_clear and written and qualifying_category
        and not voluntary_pin and not no_merchant_contact
    )

    if holds is None:
        warnings.append("Account holds/restrictions are not exposed; provisional-credit eligibility is conservatively false, but filing may proceed.")
    if not timely_statement:
        warnings.append("Timely reporting relative to the statement is not established; provisional credit is not marked required.")
    if no_merchant_contact:
        warnings.append("Customer has not contacted the ATM owner; provisional credit is not required for this non-fraud case.")
    if not written:
        warnings.append("Written statement is absent; provisional credit is not required.")
    if voluntary_pin:
        warnings.append("Voluntary PIN sharing prevents required provisional credit.")
    if category not in PROVISIONAL_CATEGORIES:
        warnings.append("This category is not one for which provisional credit is required.")

    journal = atm.get("journal_confirmed_discrepancy")
    if category == "atm_cash_discrepancy" and disputed_amount > 200:
        warnings.append("Give the Electronic Fund Transfer Error Resolution Affidavit notice.")
    if atm.get("rho_bank_owned") is False:
        warnings.append("Third-party ATM: submit to the network/owner; investigation may take up to 90 days.")
    elif atm.get("rho_bank_owned") is True and journal is True:
        warnings.append("Rho-Bank journal confirms discrepancy: arrange immediate credit after successful filing.")
    elif atm.get("rho_bank_owned") is True and journal is False:
        warnings.append("Journal does not validate the shortage; explain this but submit the formal dispute.")
    elif atm.get("rho_bank_owned") is True:
        warnings.append("No journal result is available. Submit the formal dispute; do not claim immediate confirmation or credit.")

    result = {
        "eligible_to_file": not errors,
        "errors": errors,
        "warnings": warnings,
        "open_dispute_count": open_count,
        "open_dispute_limit": limit,
        "card_action": ACTIONS.get(category),
        "provisional_credit_eligible": provisional,
    }
    if provisional:
        opened = date_value(account.get("date_opened"), "account.date_opened", [], needed=False)
        if atm.get("rho_bank_owned") is True and journal is True:
            result["provisional_credit_timing"] = "immediate_after_filing"
        elif today and opened and (today - opened).days < 30:
            result["provisional_credit_timing"] = "within_20_business_days_of_filing"
        else:
            result["provisional_credit_timing"] = "within_10_business_days_of_filing"

    if not errors:
        result["file_args"] = {
            "transaction_id": transaction["transaction_id"],
            "account_id": account_id,
            "card_id": card["card_id"],
            "user_id": card["user_id"],
            "dispute_category": category,
            "transaction_date": transaction_date_text,
            "discovery_date": discovery_text,
            "disputed_amount": disputed_amount,
            "transaction_type": transaction_type,
            "card_in_possession": case["card_in_possession"],
            "pin_compromised": case["pin_compromised"],
            "contacted_merchant": case["contacted_merchant"],
            "police_report_filed": case.get("police_report_filed", False),
            "written_statement_provided": case["written_statement_provided"],
            "provisional_credit_eligible": provisional,
            "card_action": ACTIONS.get(category),
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
