#!/usr/bin/env python3
"""Pure JSON preflight checks for debit-card dispute intake.

Input schema is documented in SKILL.md. This helper performs no I/O other than
JSON stdin/stdout and never calls banking services.
"""
import json
import sys
from datetime import datetime, date

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy",
    "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "card_present_fraud", "card_not_present_fraud",
}
TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase",
    "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
TIERS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
QUALIFYING = {
    "unauthorized_transaction", "card_present_fraud",
    "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge",
}
ACTION = {
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


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def truth(value):
    return value is True


def add_if_missing(errors, obj, fields, label):
    for field in fields:
        if obj.get(field) is None or obj.get(field) == "":
            errors.append(f"{label}: missing {field}")


def provision_result(claim, account, current):
    """Return (eligible true/false/None, reason list). None means unknown."""
    reasons = []
    category = claim.get("dispute_category")
    if category not in QUALIFYING:
        return False, ["category does not require provisional credit"]
    if not truth(claim.get("written_statement_provided")):
        return False, ["written statement not provided"]
    if account.get("status") != "OPEN" or truth(claim.get("account_has_hold_or_restriction")):
        return False, ["account is not open without holds or restrictions"]
    if claim.get("pin_compromised") == "yes_shared":
        return False, ["PIN was voluntarily shared"]
    if category not in {"card_present_fraud", "card_not_present_fraud"} and not truth(claim.get("contacted_merchant")):
        return False, ["merchant was not contacted for a non-fraud claim"]

    statement = parse_date(claim.get("statement_date"))
    discovery = parse_date(claim.get("discovery_date"))
    if statement is None or discovery is None:
        return None, ["statement date and discovery date are needed for Regulation E timeliness"]
    elapsed = (discovery - statement).days
    if elapsed < 0 or elapsed > 60:
        return False, ["report was not established within 60 days of statement date"]

    if category == "card_not_present_fraud":
        opened = parse_date(account.get("date_opened"))
        if opened is None or current is None:
            return None, ["account opening date and current date are needed for new-account assessment"]
        if (current - opened).days < 30:
            return False, ["card-not-present dispute is on an account less than 30 days old"]
    return True, ["all required provisional-credit conditions were established"]


def main(payload):
    errors = []
    warnings = []
    results = []
    account = payload.get("account") or {}
    card = payload.get("card") or {}
    transaction = payload.get("transaction") or {}
    claims = payload.get("claims") or []
    current = parse_date(payload.get("current_date"))

    if not truth(payload.get("verified")):
        errors.append("customer identity and authority have not been verified")
    add_if_missing(errors, account, ["account_id", "account_type", "account_class", "status"], "account")
    if account.get("account_type") != "checking":
        errors.append("linked account must be a checking account")
    if account.get("status") != "OPEN":
        errors.append("linked checking account must be OPEN")
    add_if_missing(errors, card, ["card_id", "account_id", "user_id"], "card")
    if card.get("account_id") and account.get("account_id") and card.get("account_id") != account.get("account_id"):
        errors.append("card is not linked to the selected checking account")

    tier = str(account.get("account_class", "")).upper().replace(" TIER", "")
    limit = TIERS.get(tier)
    if limit is None:
        errors.append("checking account tier is unsupported or missing")
    old_count = payload.get("existing_open_dispute_count")
    if not isinstance(old_count, int) or old_count < 0:
        errors.append("existing_open_dispute_count must be a non-negative integer for this account")
        old_count = 0
    if not isinstance(claims, list) or not claims:
        errors.append("at least one claim is required")
        claims = []
    if limit is not None and old_count + len(claims) > limit:
        errors.append(f"open-dispute limit exceeded: {old_count} existing plus {len(claims)} proposed exceeds {limit}")

    tx_date = parse_date(transaction.get("date"))
    tx_amount = transaction.get("amount")
    try:
        tx_abs = abs(float(tx_amount))
    except (TypeError, ValueError):
        tx_abs = None
    add_if_missing(errors, transaction, ["transaction_id", "date", "amount"], "transaction")
    if tx_abs is not None and tx_abs < 1:
        errors.append("transaction amount must be at least $1.00")
    if current is None:
        warnings.append("current_date is unavailable; 60-day transaction-age validation cannot be completed")
    elif tx_date is None:
        errors.append("transaction date must be MM/DD/YYYY")
    else:
        age = (current - tx_date).days
        if age < 0 or age > 60:
            errors.append("transaction is not within 60 days old")

    for index, claim in enumerate(claims, start=1):
        prefix = f"claim {index}"
        local_errors = []
        add_if_missing(local_errors, claim, [
            "dispute_category", "transaction_type", "transaction_date", "discovery_date",
            "disputed_amount", "card_in_possession", "pin_compromised",
            "contacted_merchant", "police_report_filed", "written_statement_provided",
        ], prefix)
        category = claim.get("dispute_category")
        transaction_type = claim.get("transaction_type")
        if category not in CATEGORIES:
            local_errors.append(f"{prefix}: invalid dispute_category")
        if transaction_type not in TYPES:
            local_errors.append(f"{prefix}: invalid transaction_type")
        if claim.get("pin_compromised") not in PINS:
            local_errors.append(f"{prefix}: invalid pin_compromised value")
        if parse_date(claim.get("transaction_date")) is None:
            local_errors.append(f"{prefix}: transaction_date must be MM/DD/YYYY")
        if parse_date(claim.get("discovery_date")) is None:
            local_errors.append(f"{prefix}: discovery_date must be MM/DD/YYYY")
        if transaction.get("date") and claim.get("transaction_date") != transaction.get("date"):
            local_errors.append(f"{prefix}: transaction_date must match the retrieved transaction date")
        try:
            disputed = float(claim.get("disputed_amount"))
            if disputed < 1:
                local_errors.append(f"{prefix}: disputed_amount must be at least $1.00")
            if tx_abs is not None and disputed > tx_abs:
                local_errors.append(f"{prefix}: disputed_amount exceeds the retrieved transaction amount")
        except (TypeError, ValueError):
            disputed = None
            local_errors.append(f"{prefix}: disputed_amount must be numeric")

        fraud = truth(claim.get("fraud_suspected"))
        if category in {"card_present_fraud", "card_not_present_fraud"} and not fraud:
            local_errors.append(f"{prefix}: fraud category requires fraud_suspected=true")
        if category == "unauthorized_transaction" and fraud:
            local_errors.append(f"{prefix}: suspected fraud requires a fraud category, not unauthorized_transaction")
        if category == "card_present_fraud" and transaction_type not in {"pin_purchase", "signature_purchase"}:
            local_errors.append(f"{prefix}: card_present_fraud requires an in-store physical purchase type")
        if category == "card_not_present_fraud" and transaction_type != "online_purchase":
            local_errors.append(f"{prefix}: card_not_present_fraud requires online_purchase")
        if category == "atm_cash_discrepancy" and transaction_type != "atm_withdrawal":
            local_errors.append(f"{prefix}: ATM cash discrepancy requires atm_withdrawal")
        if category == "atm_deposit_not_credited" and transaction_type != "atm_deposit":
            local_errors.append(f"{prefix}: ATM deposit dispute requires atm_deposit")
        if category == "recurring_charge_after_cancellation" and transaction_type != "recurring_payment":
            local_errors.append(f"{prefix}: recurring cancellation dispute requires recurring_payment")
        if category not in {"card_present_fraud", "card_not_present_fraud"} and claim.get("contacted_merchant") is None:
            local_errors.append(f"{prefix}: merchant-contact outcome is required for a non-fraud claim")
        if category in {"card_present_fraud", "card_not_present_fraud"} and disputed is not None and disputed > 500 and claim.get("police_report_filed") is False:
            warnings.append(f"{prefix}: recommend a police report for suspected fraud over $500")
        if category.startswith("atm_"):
            if claim.get("atm_owner") not in {"rho_bank", "third_party"}:
                warnings.append(f"{prefix}: identify whether the ATM is Rho-Bank or third-party")
            if category == "atm_cash_discrepancy" and disputed is not None and disputed > 200:
                warnings.append(f"{prefix}: EFT Error Resolution Affidavit is required; send to registered email and obtain return within 10 business days")
        if category == "duplicate_charge":
            candidates = claim.get("duplicate_candidates")
            if isinstance(candidates, list) and candidates:
                dates = [parse_date(item.get("date")) for item in candidates if isinstance(item, dict)]
                dates = [d for d in dates if d is not None]
                selected = parse_date(claim.get("transaction_date"))
                if dates and selected and selected != min(dates):
                    local_errors.append(f"{prefix}: select the earliest duplicate transaction")
            else:
                warnings.append(f"{prefix}: confirm this is the earliest duplicate transaction")

        eligible, reasons = provision_result(claim, account, current)
        results.append({
            "claim_index": index,
            "card_action": ACTION.get(category),
            "provisional_credit_eligible": eligible,
            "provisional_credit_reason": reasons,
            "errors": local_errors,
        })
        errors.extend(local_errors)

    return {"ok_to_file": not errors, "errors": errors, "warnings": warnings, "claims": results}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok_to_file": False, "errors": [f"invalid input: {exc}"], "warnings": [], "claims": []}, separators=(",", ":")))
