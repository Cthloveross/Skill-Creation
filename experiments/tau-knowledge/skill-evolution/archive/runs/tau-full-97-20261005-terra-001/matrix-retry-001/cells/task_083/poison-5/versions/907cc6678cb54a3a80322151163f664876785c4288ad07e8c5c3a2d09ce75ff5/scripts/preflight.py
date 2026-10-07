#!/usr/bin/env python3
"""Pure JSON preflight checks for debit-card dispute intake."""
import json
import sys
from datetime import datetime

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
TIERS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
QUALIFYING = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
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


def date_value(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def true(value):
    return value is True


def missing(errors, data, fields, label):
    for field in fields:
        if data.get(field) is None or data.get(field) == "":
            errors.append(f"{label}: missing {field}")


def tier_name(account_class):
    value = str(account_class or "").upper().strip()
    return value.replace(" TIER", "")


def provisional(claim, account, current):
    category = claim.get("dispute_category")
    if category not in QUALIFYING:
        return False, ["category does not require provisional credit"]
    if not true(claim.get("written_statement_provided")):
        return False, ["written statement not provided"]
    if account.get("status") != "OPEN" or true(claim.get("account_has_hold_or_restriction")):
        return False, ["account is not open without holds or restrictions"]
    if claim.get("pin_compromised") == "yes_shared":
        return False, ["PIN was voluntarily shared"]
    if category not in {"card_present_fraud", "card_not_present_fraud"} and not true(claim.get("contacted_merchant")):
        return False, ["merchant was not contacted for a non-fraud claim"]

    statement = date_value(claim.get("statement_date"))
    discovery = date_value(claim.get("discovery_date"))
    if statement is None or discovery is None:
        return None, ["statement date and discovery date are needed for Regulation E timeliness"]
    if (discovery - statement).days < 0 or (discovery - statement).days > 60:
        return False, ["report was not established within 60 days of statement date"]

    if category == "card_not_present_fraud":
        opened = date_value(account.get("date_opened"))
        if opened is None or current is None:
            return None, ["account opening date and current date are needed for new-account assessment"]
        if (current - opened).days < 30:
            return False, ["card-not-present dispute is on an account less than 30 days old"]
    return True, ["all required provisional-credit conditions were established"]


def validate_claim(index, claim, transaction, account, current):
    errors, warnings = [], []
    prefix = f"claim {index}"
    required = [
        "dispute_category", "transaction_type", "transaction_date", "discovery_date",
        "disputed_amount", "card_in_possession", "pin_compromised",
        "contacted_merchant", "police_report_filed", "written_statement_provided",
    ]
    missing(errors, claim, required, prefix)
    category = claim.get("dispute_category")
    transaction_type = claim.get("transaction_type")
    if category not in CATEGORIES:
        errors.append(f"{prefix}: invalid dispute_category")
    if transaction_type not in TYPES:
        errors.append(f"{prefix}: invalid transaction_type")
    if claim.get("pin_compromised") not in PINS:
        errors.append(f"{prefix}: invalid pin_compromised value")
    if date_value(claim.get("transaction_date")) is None:
        errors.append(f"{prefix}: transaction_date must be MM/DD/YYYY")
    if date_value(claim.get("discovery_date")) is None:
        errors.append(f"{prefix}: discovery_date must be MM/DD/YYYY")
    if transaction.get("date") and claim.get("transaction_date") != transaction.get("date"):
        errors.append(f"{prefix}: transaction_date must match retrieved transaction date")

    try:
        disputed = float(claim.get("disputed_amount"))
        if disputed < 1:
            errors.append(f"{prefix}: disputed_amount must be at least $1.00")
        try:
            full_amount = abs(float(transaction.get("amount")))
            if disputed > full_amount:
                errors.append(f"{prefix}: disputed_amount exceeds retrieved transaction amount")
        except (TypeError, ValueError):
            pass
    except (TypeError, ValueError):
        disputed = None
        errors.append(f"{prefix}: disputed_amount must be numeric")

    fraud = true(claim.get("fraud_suspected"))
    if category in {"card_present_fraud", "card_not_present_fraud"} and not fraud:
        errors.append(f"{prefix}: fraud category requires fraud_suspected=true")
    if category == "unauthorized_transaction" and fraud:
        errors.append(f"{prefix}: suspected fraud requires a fraud category")
    type_requirements = {
        "card_present_fraud": {"pin_purchase", "signature_purchase"},
        "card_not_present_fraud": {"online_purchase"},
        "atm_cash_discrepancy": {"atm_withdrawal"},
        "atm_deposit_not_credited": {"atm_deposit"},
        "recurring_charge_after_cancellation": {"recurring_payment"},
    }
    if category in type_requirements and transaction_type not in type_requirements[category]:
        errors.append(f"{prefix}: category does not match transaction_type")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is None:
        errors.append(f"{prefix}: merchant-contact outcome is required for a non-fraud claim")
    if category in {"card_present_fraud", "card_not_present_fraud"} and disputed is not None and disputed > 500 and claim.get("police_report_filed") is False:
        warnings.append(f"{prefix}: recommend a police report for suspected fraud over $500")
    if category.startswith("atm_"):
        if claim.get("atm_owner") not in {"rho_bank", "third_party"}:
            warnings.append(f"{prefix}: identify whether the ATM is Rho-Bank or third-party")
        if category == "atm_cash_discrepancy" and disputed is not None and disputed > 200:
            warnings.append(f"{prefix}: EFT Error Resolution Affidavit is required within 10 business days")
    if category == "duplicate_charge":
        candidates = claim.get("duplicate_candidates")
        if not isinstance(candidates, list) or not candidates:
            warnings.append(f"{prefix}: confirm selected transaction is the earliest duplicate")
        else:
            dates = [date_value(item.get("date")) for item in candidates if isinstance(item, dict)]
            dates = [item for item in dates if item is not None]
            selected = date_value(claim.get("transaction_date"))
            if dates and selected and selected != min(dates):
                errors.append(f"{prefix}: select the earliest duplicate transaction")

    eligible, reasons = provisional(claim, account, current)
    return {
        "claim_index": index,
        "card_action": ACTIONS.get(category),
        "provisional_credit_eligible": eligible,
        "provisional_credit_reason": reasons,
        "errors": errors,
    }, warnings


def main(payload):
    errors, warnings, results = [], [], []
    account = payload.get("account") or {}
    card = payload.get("card") or {}
    transaction = payload.get("transaction") or {}
    claims = payload.get("claims") or []
    current = date_value(payload.get("current_date"))

    if not true(payload.get("verified")):
        errors.append("customer identity and authority have not been verified")
    missing(errors, account, ["account_id", "account_type", "account_class", "status"], "account")
    if account.get("account_type") != "checking":
        errors.append("linked account must be a checking account")
    if account.get("status") != "OPEN":
        errors.append("linked checking account must be OPEN")
    missing(errors, card, ["card_id", "account_id", "user_id"], "card")
    if card.get("account_id") and account.get("account_id") and card["account_id"] != account["account_id"]:
        errors.append("card is not linked to the selected checking account")

    tier = tier_name(account.get("account_class"))
    limit = TIERS.get(tier)
    if limit is None:
        errors.append("checking account tier is unsupported or missing; do not infer it from an account label")
    old_count = payload.get("existing_open_dispute_count")
    if not isinstance(old_count, int) or old_count < 0:
        errors.append("existing_open_dispute_count must be a non-negative integer for this account")
        old_count = 0
    if not isinstance(claims, list) or not claims:
        errors.append("at least one claim is required")
        claims = []
    if limit is not None and old_count + len(claims) > limit:
        errors.append(f"open-dispute limit exceeded: {old_count} existing plus {len(claims)} proposed exceeds {limit}")

    missing(errors, transaction, ["transaction_id", "date", "amount"], "transaction")
    transaction_date = date_value(transaction.get("date"))
    try:
        if abs(float(transaction.get("amount"))) < 1:
            errors.append("transaction amount must be at least $1.00")
    except (TypeError, ValueError):
        errors.append("transaction amount must be numeric")
    if current is None:
        warnings.append("current_date unavailable; transaction-age validation cannot be completed")
    elif transaction_date is None:
        errors.append("transaction date must be MM/DD/YYYY")
    elif (current - transaction_date).days < 0 or (current - transaction_date).days > 60:
        errors.append("transaction is not within 60 days old")

    for index, claim in enumerate(claims, 1):
        if not isinstance(claim, dict):
            errors.append(f"claim {index}: must be an object")
            continue
        result, claim_warnings = validate_claim(index, claim, transaction, account, current)
        results.append(result)
        errors.extend(result["errors"])
        warnings.extend(claim_warnings)
    return {"ok_to_file": not errors, "errors": errors, "warnings": warnings, "claims": results}


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(source), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok_to_file": False, "errors": [f"invalid input: {exc}"], "warnings": [], "claims": []}, separators=(",", ":")))
