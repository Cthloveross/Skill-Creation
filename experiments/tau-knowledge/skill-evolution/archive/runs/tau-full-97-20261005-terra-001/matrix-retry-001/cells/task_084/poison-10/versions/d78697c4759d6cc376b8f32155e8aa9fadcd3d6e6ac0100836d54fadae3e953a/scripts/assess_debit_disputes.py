#!/usr/bin/env python3
"""Side-effect-free debit-dispute assessment.

Read one JSON object from stdin and emit:
{"ok": bool, "assessments": [{"eligible_to_file": bool, "blockers": [],
"warnings": [], "card_action": str, "provisional_credit_eligible": bool,
"capacity_basis": str}]}

Transactions use negative amounts for debits. Optional history_index is the ordinal in
an original reverse-chronological tool response (0 is newest), allowing same-date
duplicates to select the oldest/highest ordinal record.
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
OPEN = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
CAPS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
ACTIONS = {c: "keep_active" for c in CATEGORIES}
ACTIONS.update({"unauthorized_transaction": "freeze_pending_investigation",
                "card_present_fraud": "close_and_reissue",
                "card_not_present_fraud": "close_and_reissue"})
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
PROVISIONAL = FRAUD | {"unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"}


def day(v):
    return datetime.strptime(v, "%m/%d/%Y").date()


def dec(v):
    x = Decimal(str(v))
    if not x.is_finite():
        raise InvalidOperation
    return x


def tier(v):
    return str(v or "").upper().replace(" TIER", "").strip()


def main(data):
    required = ["current_date", "user_verified", "user_id", "accounts", "cards",
                "transactions", "existing_disputes", "proposed_disputes"]
    missing = [x for x in required if x not in data]
    if missing or not isinstance(data.get("user_verified"), bool):
        return {"ok": False, "input_errors": ["Missing required fields or invalid user_verified."], "assessments": []}
    try:
        now = day(data["current_date"])
    except (ValueError, TypeError):
        return {"ok": False, "input_errors": ["current_date must be MM/DD/YYYY."], "assessments": []}
    if any(not isinstance(data[x], list) for x in required[3:]):
        return {"ok": False, "input_errors": ["Collection fields must be arrays."], "assessments": []}

    accounts = {x.get("account_id"): x for x in data["accounts"] if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data["cards"] if x.get("card_id")}
    txs = {x.get("transaction_id"): x for x in data["transactions"] if x.get("transaction_id")}
    counts = {}
    for d in data["existing_disputes"]:
        if d.get("status") in OPEN:
            counts[d.get("account_id")] = counts.get(d.get("account_id"), 0) + 1

    # Earliest means lowest date, then highest reverse-chronological ordinal.
    earliest = {}
    for i, p in enumerate(data["proposed_disputes"]):
        group, tx = p.get("duplicate_group"), txs.get(p.get("transaction_id"), {})
        if not group:
            continue
        try:
            key = (day(tx.get("date")), -int(tx.get("history_index", 0)))
        except (ValueError, TypeError):
            key = (datetime.max.date(), 0)
        if group not in earliest or key < earliest[group][0]:
            earliest[group] = (key, i)

    planned = dict(counts)
    out = []
    for i, p in enumerate(data["proposed_disputes"]):
        b, w = [], []
        aid, cid, tid = p.get("account_id"), p.get("card_id"), p.get("transaction_id")
        account, card, tx = accounts.get(aid), cards.get(cid), txs.get(tid)
        category = p.get("dispute_category")
        if not data["user_verified"]: b.append("Customer is not verified.")
        if category not in CATEGORIES: b.append("Invalid dispute category.")
        if p.get("transaction_type") not in TYPES: b.append("Invalid transaction type.")
        if p.get("pin_compromised") not in {"yes_shared", "yes_observed", "no", "unknown"}: b.append("Invalid PIN status.")
        if not isinstance(p.get("card_in_possession"), bool): b.append("card_in_possession must be boolean.")
        if not isinstance(p.get("contacted_merchant"), bool): b.append("contacted_merchant must be boolean.")
        if not isinstance(p.get("written_statement_provided"), bool): b.append("written_statement_provided must be boolean.")
        if not account or account.get("account_type") != "checking" or account.get("status") != "OPEN": b.append("No matching OPEN checking account.")
        if not card or card.get("account_id") != aid or card.get("user_id") != data["user_id"]: b.append("No matching customer debit card.")
        try:
            age = (now - day(tx.get("date"))).days
            amount, claim = dec(tx.get("amount")), dec(p.get("disputed_amount"))
            if age < 0 or age > 60: b.append("Transaction is outside the 60-day filing window.")
            if amount >= 0 or abs(amount) < 1: b.append("Transaction is not an eligible debit of at least $1.")
            if claim <= 0 or claim > abs(amount): b.append("Invalid disputed amount.")
            if day(p.get("discovery_date")) > now: b.append("Discovery date is in the future.")
        except (AttributeError, ValueError, TypeError, InvalidOperation): b.append("Transaction/date/amount data is invalid or missing.")
        if category == "unauthorized_transaction" and p.get("fraud_suspected") is True: b.append("Suspected fraud requires a fraud category.")
        if category in FRAUD and p.get("fraud_suspected") is not True: b.append("Fraud category requires suspected fraud.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"} and p.get("atm_operator") not in {"rho_bank", "third_party"}: b.append("ATM operator is required.")
        group = p.get("duplicate_group")
        if group and earliest.get(group, (None, i))[1] != i: b.append("Only earliest duplicate may be filed.")

        known_cap = CAPS.get(tier(account.get("account_class") if account else None))
        used = planned.get(aid, 0)
        cap = known_cap or 2
        basis = "account-tier cap" if known_cap else "published minimum cap of 2"
        if used >= cap: b.append("Open-dispute capacity is exhausted.")
        elif not known_cap: w.append("Tier unavailable; capacity limited conservatively to the published minimum.")

        standing = bool(account and account.get("status") == "OPEN" and account.get("has_holds") is False and account.get("has_restrictions") is False)
        timely = p.get("reported_within_60_days_of_statement") is True
        eligible_credit = bool(timely and category in PROVISIONAL and p.get("written_statement_provided") is True and standing and p.get("pin_compromised") != "yes_shared")
        if p.get("reported_within_60_days_of_statement") is not True: w.append("Statement-date timeliness is unestablished; do not promise provisional credit.")
        if account and not standing: w.append("Account standing is unestablished; do not promise provisional credit.")
        if not b: planned[aid] = used + 1
        out.append({"proposal_index": i, "transaction_id": tid, "eligible_to_file": not b,
                    "blockers": b, "warnings": w, "card_action": ACTIONS.get(category),
                    "provisional_credit_eligible": eligible_credit, "capacity_basis": basis,
                    "open_disputes_after_if_filed": planned.get(aid, used)})
    return {"ok": True, "assessments": out}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "input_errors": [str(exc)], "assessments": []}))
