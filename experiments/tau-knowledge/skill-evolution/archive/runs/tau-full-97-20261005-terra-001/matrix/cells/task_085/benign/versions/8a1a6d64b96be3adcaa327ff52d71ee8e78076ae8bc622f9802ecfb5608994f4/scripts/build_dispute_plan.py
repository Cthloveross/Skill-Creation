#!/usr/bin/env python3
"""Build a validated filing plan for an ATM debit-card dispute.

Reads one JSON object from stdin and writes one JSON object to stdout. This
helper is deterministic and never invokes banking tools or changes bank state.
"""
import json
import sys
from datetime import datetime

DATE_FMT = "%m/%d/%Y"
OPEN_DISPUTE_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED",
}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
STATEMENT_TIMINGS = {
    "within_2_business_days", "within_60_days", "after_60_days", "unknown",
}
ACTIONS = {
    "atm_cash_discrepancy": "keep_active",
    "atm_deposit_not_credited": "keep_active",
}
PROVISIONAL_CATEGORIES = {"atm_cash_discrepancy"}


def required(mapping, key, errors, label=None):
    if key not in mapping:
        errors.append("Missing " + (label or key) + ".")
        return None
    return mapping[key]


def parse_date(value, label, errors, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None


def is_bool(value):
    return isinstance(value, bool)


def account_tier(value):
    text = str(value or "").lower().replace("_", " ").replace("-", " ")
    for tier in LIMITS:
        if tier in text:
            return tier
    return None


def numeric(value, label, errors):
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric.")
        return None


def main(data):
    errors, warnings = [], []
    account = data.get("account") if isinstance(data.get("account"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    transaction = data.get("transaction") if isinstance(data.get("transaction"), dict) else {}
    case = data.get("case") if isinstance(data.get("case"), dict) else {}
    atm = data.get("atm") if isinstance(data.get("atm"), dict) else {}

    today_text = required(data, "today", errors)
    today = parse_date(today_text, "today", errors)
    transaction_date_text = required(transaction, "date", errors, "transaction.date")
    transaction_date = parse_date(transaction_date_text, "transaction.date", errors)
    discovery_text = required(case, "discovery_date", errors, "case.discovery_date")
    discovery_date = parse_date(discovery_text, "case.discovery_date", errors)

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
    if card.get("status") and str(card["status"]).upper() != "ACTIVE":
        warnings.append("Selected card is not marked ACTIVE; confirm it is the appropriate linked card before filing.")
    if not transaction.get("transaction_id"):
        errors.append("Missing transaction.transaction_id.")
    if transaction.get("status") and str(transaction["status"]).lower() != "posted":
        errors.append("The disputed ATM transaction must be posted.")

    transaction_amount = numeric(
        required(transaction, "amount", errors, "transaction.amount"),
        "transaction.amount", errors,
    )
    disputed_amount = numeric(
        required(case, "disputed_amount", errors, "case.disputed_amount"),
        "case.disputed_amount", errors,
    )
    if transaction_amount is not None and abs(transaction_amount) < 1:
        errors.append("The transaction must be at least $1.00.")
    if disputed_amount is not None:
        if disputed_amount < 1:
            errors.append("The disputed amount must be at least $1.00.")
        if transaction_amount is not None and disputed_amount > abs(transaction_amount):
            errors.append("The disputed amount cannot exceed the transaction amount.")

    if today and transaction_date:
        age = (today - transaction_date).days
        if age < 0:
            errors.append("Transaction date cannot be after filing date.")
        elif age > 60:
            errors.append("Transaction is more than 60 days old and cannot be filed through this workflow.")
    if transaction_date and discovery_date and discovery_date < transaction_date:
        errors.append("Discovery date cannot precede transaction date.")

    category = required(case, "category", errors, "case.category")
    transaction_type = required(case, "transaction_type", errors, "case.transaction_type")
    if category not in ACTIONS:
        errors.append("case.category must be an ATM cash discrepancy or ATM deposit-not-credited category.")
    if category == "atm_cash_discrepancy":
        if transaction_type != "atm_withdrawal":
            errors.append("ATM cash discrepancy must use transaction_type atm_withdrawal.")
        if transaction_amount is not None and transaction_amount >= 0:
            errors.append("An ATM withdrawal transaction must be a debit amount.")
    if category == "atm_deposit_not_credited":
        if transaction_type != "atm_deposit":
            errors.append("ATM deposit not credited must use transaction_type atm_deposit.")
        if transaction_amount is not None and transaction_amount <= 0:
            errors.append("An ATM deposit transaction must be a credit amount.")
    if transaction.get("type") and transaction_type != transaction.get("type"):
        errors.append("case.transaction_type must match transaction.type.")

    for field in ("card_in_possession", "contacted_merchant", "written_statement_provided"):
        if not is_bool(case.get(field)):
            errors.append(f"case.{field} must be boolean.")
    if case.get("pin_compromised") not in PIN_VALUES:
        errors.append("case.pin_compromised must be yes_shared, yes_observed, no, or unknown.")
    if "police_report_filed" in case and not is_bool(case["police_report_filed"]):
        errors.append("case.police_report_filed must be boolean when supplied.")
    if not is_bool(atm.get("rho_bank_owned")):
        errors.append("atm.rho_bank_owned must be boolean.")

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
    tier = account_tier(account.get("account_class"))
    if tier:
        dispute_limit = LIMITS[tier]
        if open_count >= dispute_limit:
            errors.append(f"Open-dispute limit reached for this account ({open_count}/{dispute_limit}).")
    else:
        dispute_limit = LIMITS["entry"]
        if open_count >= dispute_limit:
            errors.append("Account tier is required to establish remaining dispute capacity.")
        else:
            warnings.append("Account tier was not exposed; capacity is established using the Entry-tier limit.")

    timing = case.get("statement_timing", "unknown")
    if timing not in STATEMENT_TIMINGS:
        warnings.append("Statement timing is invalid or unavailable; provisional-credit eligibility is conservatively false.")
        timing = "unknown"

    holds = account.get("holds_or_restrictions")
    if holds is not None and not is_bool(holds):
        errors.append("account.holds_or_restrictions must be boolean or null when supplied.")

    timely_statement = timing in {"within_2_business_days", "within_60_days"}
    account_clear = account.get("status") == "OPEN" and holds is False
    written = case.get("written_statement_provided") is True
    qualifying_category = category in PROVISIONAL_CATEGORIES
    voluntary_pin = case.get("pin_compromised") == "yes_shared"
    no_merchant_contact = case.get("contacted_merchant") is False
    provisional = bool(
        timely_statement and account_clear and written and qualifying_category
        and not voluntary_pin and not no_merchant_contact
    )
    if holds is None:
        warnings.append("Account holds/restrictions are not exposed; provisional-credit eligibility is conservatively false, but this does not block filing.")
    if not timely_statement:
        warnings.append("Timely reporting relative to the statement is not established; provisional credit is not marked required.")
    if no_merchant_contact:
        warnings.append("Customer has not contacted the ATM owner; required provisional credit does not apply to this non-fraud case.")
    if not written:
        warnings.append("Written statement is absent; provisional credit is not required.")
    if voluntary_pin:
        warnings.append("Voluntary PIN sharing prevents required provisional credit.")
    if category not in PROVISIONAL_CATEGORIES:
        warnings.append("This category is not one for which provisional credit is required.")

    journal = atm.get("journal_confirmed_discrepancy")
    if category == "atm_cash_discrepancy" and disputed_amount is not None and disputed_amount > 200:
        warnings.append("Give the Electronic Fund Transfer Error Resolution Affidavit notice.")
    if atm.get("rho_bank_owned") is False:
        warnings.append("Third-party ATM: submit to the network/owner; investigation may take up to 90 days.")
    elif atm.get("rho_bank_owned") is True and journal is True:
        warnings.append("Rho-Bank journal confirms discrepancy: arrange immediate credit after successful filing.")
    elif atm.get("rho_bank_owned") is True and journal is False:
        warnings.append("Journal does not validate the shortage; explain this but submit the formal dispute when filing inputs are complete.")
    elif atm.get("rho_bank_owned") is True:
        warnings.append("No journal result is available. Do not claim immediate confirmation or credit; file when filing inputs are complete.")

    result = {
        "eligible_to_file": not errors,
        "errors": errors,
        "warnings": warnings,
        "open_dispute_count": open_count,
        "open_dispute_limit": dispute_limit,
        "card_action": ACTIONS.get(category),
        "provisional_credit_eligible": provisional,
    }
    if provisional:
        opened = parse_date(account.get("date_opened"), "account.date_opened", [], optional=True)
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
            "card_action": ACTIONS[category],
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
