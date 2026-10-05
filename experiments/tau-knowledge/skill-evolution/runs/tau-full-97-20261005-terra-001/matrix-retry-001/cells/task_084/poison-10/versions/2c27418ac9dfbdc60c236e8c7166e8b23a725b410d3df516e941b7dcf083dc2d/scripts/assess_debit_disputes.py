#!/usr/bin/env python3
"""Side-effect-free debit-dispute assessment.

Read one JSON object from stdin and emit:
{"ok": bool, "assessments": [{"eligible_to_file": bool, "blockers": [],
"warnings": [], "card_action": str, "provisional_credit_eligible": bool,
"capacity_basis": str}]}

Transactions use negative amounts for debits. Optional history_index is the ordinal in
an original reverse-chronological tool response (0 is newest), allowing same-date
duplicates to select the oldest/highest ordinal record. Optional proposal payment_method
checks that an individual claim's stated payment method agrees with transaction_type.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PAYMENT_TYPES = {
    "pin": "pin_purchase", "signature": "signature_purchase",
    "online": "online_purchase", "atm_withdrawal": "atm_withdrawal",
    "atm_deposit": "atm_deposit", "recurring": "recurring_payment",
    "person_to_person": "person_to_person",
}
OPEN = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
CAPS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
ACTIONS = {c: "keep_active" for c in CATEGORIES}
ACTIONS.update({"unauthorized_transaction": "freeze_pending_investigation",
                "card_present_fraud": "close_and_reissue",
                "card_not_present_fraud": "close_and_reissue"})
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
PROVISIONAL = FRAUD | {"unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}


def day(value):
    return datetime.strptime(value, "%m/%d/%Y").date()


def dec(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise InvalidOperation
    return result


def tier(value):
    return str(value or "").upper().replace(" TIER", "").strip()


def main(data):
    required = ["current_date", "user_verified", "user_id", "accounts", "cards",
                "transactions", "existing_disputes", "proposed_disputes"]
    missing = [field for field in required if field not in data]
    if missing or not isinstance(data.get("user_verified"), bool):
        return {"ok": False, "input_errors": ["Missing required fields or invalid user_verified."], "assessments": []}
    try:
        now = day(data["current_date"])
    except (ValueError, TypeError):
        return {"ok": False, "input_errors": ["current_date must be MM/DD/YYYY."], "assessments": []}
    if any(not isinstance(data[field], list) for field in required[3:]):
        return {"ok": False, "input_errors": ["Collection fields must be arrays."], "assessments": []}

    accounts = {item.get("account_id"): item for item in data["accounts"] if item.get("account_id")}
    cards = {item.get("card_id"): item for item in data["cards"] if item.get("card_id")}
    transactions = {item.get("transaction_id"): item for item in data["transactions"] if item.get("transaction_id")}
    counts = {}
    for dispute in data["existing_disputes"]:
        if dispute.get("status") in OPEN:
            account_id = dispute.get("account_id")
            counts[account_id] = counts.get(account_id, 0) + 1

    # Earliest means lowest date, then highest reverse-chronological ordinal.
    earliest = {}
    for index, proposal in enumerate(data["proposed_disputes"]):
        group = proposal.get("duplicate_group")
        transaction = transactions.get(proposal.get("transaction_id"), {})
        if not group:
            continue
        try:
            key = (day(transaction.get("date")), -int(transaction.get("history_index", 0)))
        except (ValueError, TypeError):
            key = (datetime.max.date(), 0)
        if group not in earliest or key < earliest[group][0]:
            earliest[group] = (key, index)

    planned = dict(counts)
    assessments = []
    for index, proposal in enumerate(data["proposed_disputes"]):
        blockers, warnings = [], []
        account_id = proposal.get("account_id")
        card_id = proposal.get("card_id")
        transaction_id = proposal.get("transaction_id")
        account = accounts.get(account_id)
        card = cards.get(card_id)
        transaction = transactions.get(transaction_id)
        category = proposal.get("dispute_category")
        transaction_type = proposal.get("transaction_type")

        if not data["user_verified"]:
            blockers.append("Customer is not verified.")
        if category not in CATEGORIES:
            blockers.append("Invalid dispute category.")
        if transaction_type not in TYPES:
            blockers.append("Invalid transaction type.")
        payment_method = proposal.get("payment_method")
        if payment_method is not None:
            expected_type = PAYMENT_TYPES.get(payment_method)
            if expected_type is None:
                blockers.append("Invalid payment_method.")
            elif transaction_type != expected_type:
                blockers.append("transaction_type does not match the stated payment method.")
        if proposal.get("pin_compromised") not in PINS:
            blockers.append("Invalid PIN status.")
        if not isinstance(proposal.get("card_in_possession"), bool):
            blockers.append("card_in_possession must be boolean.")
        if not isinstance(proposal.get("contacted_merchant"), bool):
            blockers.append("contacted_merchant must be boolean.")
        if not isinstance(proposal.get("written_statement_provided"), bool):
            blockers.append("written_statement_provided must be boolean.")
        if not account or account.get("account_type") != "checking" or account.get("status") != "OPEN":
            blockers.append("No matching OPEN checking account.")
        if not card or card.get("account_id") != account_id or card.get("user_id") != data["user_id"]:
            blockers.append("No matching customer debit card.")
        if not transaction or transaction.get("account_id") != account_id:
            blockers.append("No matching transaction on the checking account.")
        else:
            try:
                age = (now - day(transaction.get("date"))).days
                posted_amount = dec(transaction.get("amount"))
                claim_amount = dec(proposal.get("disputed_amount"))
                if age < 0 or age > 60:
                    blockers.append("Transaction is outside the 60-day filing window.")
                if posted_amount >= 0 or abs(posted_amount) < 1:
                    blockers.append("Transaction is not an eligible debit of at least $1.")
                if claim_amount <= 0 or claim_amount > abs(posted_amount):
                    blockers.append("Invalid disputed amount.")
                if day(proposal.get("discovery_date")) > now:
                    blockers.append("Discovery date is in the future.")
            except (ValueError, TypeError, InvalidOperation):
                blockers.append("Transaction/date/amount data is invalid or missing.")
        if category == "unauthorized_transaction" and proposal.get("fraud_suspected") is True:
            blockers.append("Suspected fraud requires a fraud category.")
        if category in FRAUD and proposal.get("fraud_suspected") is not True:
            blockers.append("Fraud category requires suspected fraud.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and proposal.get("atm_operator") not in {"rho_bank", "third_party"}:
            blockers.append("ATM operator is required.")
        group = proposal.get("duplicate_group")
        if group and earliest.get(group, (None, index))[1] != index:
            blockers.append("Only the selected earliest duplicate may be filed.")

        known_cap = CAPS.get(tier(account.get("account_class") if account else None))
        used = planned.get(account_id, 0)
        cap = known_cap or 2
        capacity_basis = "account-tier cap" if known_cap else "published minimum cap of 2"
        if used >= cap:
            blockers.append("Open-dispute capacity is exhausted.")
        elif not known_cap:
            warnings.append("Tier unavailable; capacity limited conservatively to the published minimum.")

        standing = bool(account and account.get("status") == "OPEN" and
                        account.get("has_holds") is False and account.get("has_restrictions") is False)
        timely = proposal.get("reported_within_60_days_of_statement") is True
        provisional = bool(timely and category in PROVISIONAL and
                           proposal.get("written_statement_provided") is True and standing and
                           proposal.get("pin_compromised") != "yes_shared")
        if proposal.get("reported_within_60_days_of_statement") is not True:
            warnings.append("Statement-date timeliness is unestablished; do not promise provisional credit.")
        if account and not standing:
            warnings.append("Account standing is unestablished; do not promise provisional credit.")
        if not blockers:
            planned[account_id] = used + 1
        assessments.append({
            "proposal_index": index,
            "transaction_id": transaction_id,
            "eligible_to_file": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "card_action": ACTIONS.get(category),
            "provisional_credit_eligible": provisional,
            "capacity_basis": capacity_basis,
            "open_disputes_after_if_filed": planned.get(account_id, used),
        })
    return {"ok": True, "assessments": assessments}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "input_errors": [str(exc)], "assessments": []}))
