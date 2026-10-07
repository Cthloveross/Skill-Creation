#!/usr/bin/env python3
"""Deterministic preflight validation for debit-card dispute filings.

Reads one JSON object from stdin and writes:
{"ok": bool, "errors": [str], "warnings": [str], "decisions": [object]}
No bank records are read or modified.
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
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
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
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def add(issue_list, prefix, message):
    issue_list.append(f"{prefix}: {message}")


def main(payload):
    errors, warnings, decisions = [], [], []
    account = payload.get("account") or {}
    card = payload.get("card") or {}
    disputes = payload.get("disputes") or []
    today = parse_date(payload.get("today"))

    if not payload.get("verified"):
        add(errors, "case", "customer identity has not been verified")
    if account.get("status") != "OPEN":
        add(errors, "case", "linked checking account is not OPEN")
    if not account.get("account_id"):
        add(errors, "case", "missing checking account ID")
    if not card.get("card_id"):
        add(errors, "case", "missing debit card ID")
    if card.get("account_id") != account.get("account_id"):
        add(errors, "case", "card is not linked to the selected checking account")
    if account.get("has_hold_or_restriction"):
        add(warnings, "case", "account has a hold/restriction; required provisional credit cannot be determined as eligible")

    tier = str(account.get("tier", "")).strip().lower().replace(" tier", "")
    limit = LIMITS.get(tier)
    open_count = sum(
        1 for d in (payload.get("open_disputes") or [])
        if d.get("account_id") == account.get("account_id") and d.get("status") == "OPEN"
    )
    if limit is None:
        add(errors, "case", "unknown checking-account tier; cannot check open-dispute limit")
    elif open_count + len(disputes) > limit:
        add(errors, "case", f"{open_count} existing OPEN dispute(s) plus {len(disputes)} requested exceeds {tier.title()} limit of {limit}")

    if not isinstance(disputes, list) or not disputes:
        add(errors, "case", "no disputes supplied")

    account_opened = parse_date(account.get("date_opened"))
    new_account = bool(today and account_opened and (today - account_opened).days < 30)

    for index, item in enumerate(disputes, 1):
        prefix = f"dispute[{index}]"
        tx = item.get("transaction") or {}
        category = item.get("dispute_category")
        tx_date = parse_date(item.get("transaction_date"))
        discovery = parse_date(item.get("discovery_date"))
        tx_amount = tx.get("amount")
        disputed = item.get("disputed_amount")

        if not tx.get("transaction_id"):
            add(errors, prefix, "missing matched transaction_id")
        if tx.get("account_id") != account.get("account_id"):
            add(errors, prefix, "matched transaction belongs to another account")
        if tx.get("type") not in {"debit_card_purchase", "atm_withdrawal", "everyonepay"}:
            add(warnings, prefix, "transaction type is not a usual debit-card/ATM/P2P type; confirm it is eligible")
        if category not in CATEGORIES:
            add(errors, prefix, "invalid dispute category")
        if item.get("transaction_type") not in TYPES:
            add(errors, prefix, "invalid transaction_type")
        if item.get("pin_compromised") not in PINS:
            add(errors, prefix, "invalid pin_compromised value")
        if not isinstance(item.get("card_in_possession"), bool):
            add(errors, prefix, "card_in_possession must be boolean")
        if not isinstance(item.get("contacted_merchant"), bool):
            add(errors, prefix, "contacted_merchant must be boolean")
        if not isinstance(item.get("written_statement_provided"), bool):
            add(errors, prefix, "written_statement_provided must be boolean")
        if tx_date is None:
            add(errors, prefix, "invalid transaction_date")
        if discovery is None:
            add(errors, prefix, "invalid discovery_date")
        if tx_date and discovery and discovery < tx_date:
            add(errors, prefix, "discovery_date precedes transaction_date")
        if tx.get("date") and tx.get("date") != item.get("transaction_date"):
            add(errors, prefix, "filing transaction_date does not match retrieved transaction date")
        if today is None:
            add(warnings, prefix, "today is absent/invalid; 60-day transaction age was not checked")
        elif tx_date and (today - tx_date).days > 60:
            add(errors, prefix, "transaction is more than 60 days old")
        elif tx_date and tx_date > today:
            add(errors, prefix, "transaction date is in the future")

        try:
            disputed_number = float(disputed)
            tx_number = abs(float(tx_amount))
            if disputed_number < 1:
                add(errors, prefix, "disputed amount must be at least $1.00")
            if disputed_number > tx_number:
                add(errors, prefix, "disputed amount exceeds the transaction amount")
        except (TypeError, ValueError):
            add(errors, prefix, "transaction amount and disputed amount must be numeric")
            disputed_number = None

        fraud = item.get("fraud_suspected")
        channel = item.get("channel")
        if category in FRAUD_CATEGORIES and fraud is not True:
            add(errors, prefix, "fraud category requires fraud_suspected=true")
        if category == "unauthorized_transaction" and fraud is True:
            add(errors, prefix, "suspected fraud must use a card-present or card-not-present fraud category")
        if category == "card_present_fraud" and channel not in {"physical", "in_store"}:
            add(errors, prefix, "card_present_fraud requires physical/in-store channel")
        if category == "card_not_present_fraud" and channel not in {"online", "phone", "online_phone"}:
            add(errors, prefix, "card_not_present_fraud requires online/phone channel")
        if category == "atm_cash_discrepancy" and item.get("transaction_type") != "atm_withdrawal":
            add(errors, prefix, "ATM cash discrepancy requires atm_withdrawal transaction_type")
        if category == "atm_deposit_not_credited" and item.get("transaction_type") != "atm_deposit":
            add(errors, prefix, "ATM deposit claim requires atm_deposit transaction_type")
        if category == "recurring_charge_after_cancellation" and item.get("transaction_type") != "recurring_payment":
            add(errors, prefix, "recurring-after-cancellation claim requires recurring_payment transaction_type")
        if category == "duplicate_charge":
            candidates = item.get("duplicate_candidates") or []
            parsed = [(parse_date(c.get("date")), c.get("transaction_id")) for c in candidates]
            earlier = [x for x in parsed if x[0] and tx_date and x[0] < tx_date]
            if earlier:
                add(errors, prefix, "a supplied duplicate candidate is earlier; dispute the first transaction")
            elif not candidates:
                add(warnings, prefix, "no duplicate candidates supplied; confirm this is the earliest duplicate")

        statement_timely = item.get("reported_within_60_days_of_statement") is True
        nonfraud_uncontacted = category not in FRAUD_CATEGORIES and not item.get("contacted_merchant", False)
        pin_shared = item.get("pin_compromised") == "yes_shared"
        cnp_new = new_account and category == "card_not_present_fraud"
        eligible = (
            statement_timely and category in PC_CATEGORIES and
            item.get("written_statement_provided") is True and
            account.get("status") == "OPEN" and not account.get("has_hold_or_restriction") and
            not nonfraud_uncontacted and not pin_shared and not cnp_new
        )
        if not statement_timely:
            add(warnings, prefix, "statement-date timeliness is unconfirmed; required provisional credit is not established")
        if category in PC_CATEGORIES and not item.get("written_statement_provided", False):
            add(warnings, prefix, "written statement is required to establish required provisional credit")
        if nonfraud_uncontacted:
            add(warnings, prefix, "merchant contact is required for this non-fraud claim before required provisional credit")
        if pin_shared:
            add(warnings, prefix, "voluntarily shared PIN prevents required provisional credit")
        if cnp_new:
            add(warnings, prefix, "new-account card-not-present claim does not require provisional credit")
        decisions.append({
            "index": index,
            "card_action": ACTIONS.get(category),
            "provisional_credit_eligible": eligible,
            "provisional_credit_amount": disputed_number if eligible else None,
            "provisional_credit_deadline_business_days": 20 if new_account else 10 if eligible else None,
        })

    return {"ok": not errors, "errors": errors, "warnings": warnings, "decisions": decisions}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [f"input: {exc}"], "warnings": [], "decisions": []}))
        sys.exit(1)
