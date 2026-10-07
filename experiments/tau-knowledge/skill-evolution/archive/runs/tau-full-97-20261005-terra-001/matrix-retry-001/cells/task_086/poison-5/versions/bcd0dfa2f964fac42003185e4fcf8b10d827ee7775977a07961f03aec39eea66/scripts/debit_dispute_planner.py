#!/usr/bin/env python3
"""Validate normalized debit-dispute data and produce tool-ready filing payloads.
Reads one JSON object from stdin and writes one JSON object to stdout.
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
TRANSACTION_TYPES = {
    "pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
    "atm_deposit", "recurring_payment", "person_to_person",
}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
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
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
QUALIFYING_PC = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
EXCLUDED_PC = {
    "goods_services_not_received", "recurring_charge_after_cancellation",
    "atm_deposit_not_credited", "incorrect_amount",
}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value)).copy_abs()
    except (InvalidOperation, ValueError, TypeError):
        return None


def boolean(value):
    return isinstance(value, bool)


def account_age_days(account, as_of):
    opened = parse_date(account.get("date_opened"))
    if not opened:
        return None
    return (as_of - opened).days


def provisional(case, account, as_of):
    """Return (boolean-or-None, reasons, blockers). None means facts are insufficient."""
    category = case.get("dispute_category")
    reasons, blockers = [], []
    if category in EXCLUDED_PC:
        return False, ["category is not provisionally-credit eligible"], blockers
    if case.get("pin_compromised") == "yes_shared":
        return False, ["PIN was voluntarily shared"], blockers
    if category not in QUALIFYING_PC:
        return False, ["category is not provisionally-credit eligible"], blockers
    age = account_age_days(account, as_of)
    if category == "card_not_present_fraud" and age is not None and age < 30:
        return False, ["new-account card-not-present exclusion"], blockers
    if not case.get("written_statement_provided"):
        return False, ["written statement not provided"], blockers
    if account.get("status") != "OPEN" or account.get("has_holds") or account.get("has_restrictions"):
        return False, ["account is not open and unrestricted"], blockers
    timely = case.get("timely_reporting_within_60_days_of_statement")
    if timely is None:
        statement = parse_date(case.get("statement_date"))
        discovery = parse_date(case.get("discovery_date"))
        if statement and discovery:
            timely = 0 <= (discovery - statement).days <= 60
    if timely is None:
        blockers.append("cannot determine provisional-credit eligibility without statement date or timely_reporting_within_60_days_of_statement")
        return None, reasons, blockers
    if timely is not True:
        return False, ["report was not timely relative to statement date"], blockers
    if category not in {"card_present_fraud", "card_not_present_fraud"} and not boolean(case.get("contacted_merchant")):
        blockers.append("contacted_merchant must be a boolean")
    elif category not in {"card_present_fraud", "card_not_present_fraud"} and not case.get("contacted_merchant"):
        return False, ["merchant was not contacted for non-fraud dispute"], blockers
    return True, ["all required provisional-credit conditions are established"], blockers


def main(data):
    as_of = parse_date(data.get("as_of"))
    if not as_of:
        return {"error": "as_of is required in MM/DD/YYYY format", "filings": []}
    if data.get("verified") is not True:
        return {"error": "customer identity must be verified before planning banking actions", "filings": []}

    accounts = {a.get("account_id"): a for a in data.get("accounts", []) if a.get("account_id")}
    cards = {c.get("card_id"): c for c in data.get("cards", []) if c.get("card_id")}
    transactions = {t.get("transaction_id"): t for t in data.get("transactions", []) if t.get("transaction_id")}
    open_disputes = data.get("open_disputes", [])
    existing_by_account = {}
    existing_transaction_ids = set()
    for dispute in open_disputes:
        if str(dispute.get("status", "")).upper() in OPEN_STATUSES:
            aid = dispute.get("account_id")
            existing_by_account[aid] = existing_by_account.get(aid, 0) + 1
            if dispute.get("transaction_id"):
                existing_transaction_ids.add(dispute["transaction_id"])

    planned_by_account = {}
    filings, case_results = [], []
    action_by_card = {}
    duplicate_groups = {}
    for i, case in enumerate(data.get("disputes", [])):
        group = case.get("duplicate_group")
        if case.get("dispute_category") == "duplicate_charge" and group:
            duplicate_groups.setdefault(group, []).append(case)

    for index, case in enumerate(data.get("disputes", [])):
        errors, warnings = [], []
        aid, cid, uid, tid = (case.get("account_id"), case.get("card_id"), case.get("user_id"), case.get("transaction_id"))
        account, card, txn = accounts.get(aid), cards.get(cid), transactions.get(tid)
        category = case.get("dispute_category")
        tx_date = parse_date(case.get("transaction_date"))
        discovery = parse_date(case.get("discovery_date"))
        amount = money(case.get("disputed_amount"))

        if not account:
            errors.append("affected account was not found")
        else:
            if str(account.get("account_type", "")).lower() != "checking":
                errors.append("debit card disputes require a checking account")
            if account.get("status") != "OPEN":
                errors.append("linked checking account is not OPEN")
            tier = str(account.get("tier", "")).lower()
            if tier not in LIMITS:
                errors.append("account tier is missing or unsupported for dispute-limit validation")
        if not card:
            errors.append("debit card was not found")
        elif card.get("account_id") != aid or card.get("user_id") != uid:
            errors.append("card does not belong to the supplied user and checking account")
        if not txn:
            errors.append("transaction was not found in retrieved account history")
        else:
            if txn.get("account_id") != aid:
                errors.append("transaction does not belong to the selected account")
            actual_date = parse_date(txn.get("date"))
            if not tx_date or actual_date != tx_date:
                errors.append("transaction_date does not exactly match the retrieved transaction")
            txn_amount = money(txn.get("amount"))
            if txn_amount is None or txn_amount < Decimal("1.00"):
                errors.append("underlying transaction must be at least $1.00")
            if amount is not None and txn_amount is not None and amount > txn_amount:
                errors.append("disputed amount exceeds the underlying transaction amount")
        if tid in existing_transaction_ids:
            errors.append("an unresolved dispute already exists for this transaction")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        if case.get("transaction_type") not in TRANSACTION_TYPES:
            errors.append("transaction_type is invalid")
        if not tx_date:
            errors.append("transaction_date must use MM/DD/YYYY")
        elif tx_date > as_of or (as_of - tx_date).days > 60:
            errors.append("transaction is outside the 60-day filing window")
        if not discovery:
            errors.append("discovery_date must use MM/DD/YYYY")
        elif discovery > as_of:
            errors.append("discovery_date is in the future relative to filing date")
        if amount is None or amount < Decimal("1.00"):
            errors.append("disputed_amount must be at least $1.00")
        if not boolean(case.get("card_in_possession")):
            errors.append("card_in_possession must be boolean")
        if case.get("pin_compromised") not in PINS:
            errors.append("pin_compromised is invalid")
        if not boolean(case.get("contacted_merchant")):
            errors.append("contacted_merchant must be boolean")
        if not boolean(case.get("police_report_filed")):
            errors.append("police_report_filed must be boolean")
        if not boolean(case.get("written_statement_provided")):
            errors.append("written_statement_provided must be boolean")
        if category == "atm_cash_discrepancy" and case.get("transaction_type") != "atm_withdrawal":
            errors.append("ATM cash discrepancy requires transaction_type atm_withdrawal")
        if category == "atm_deposit_not_credited" and case.get("transaction_type") != "atm_deposit":
            errors.append("ATM deposit dispute requires transaction_type atm_deposit")
        if category == "card_not_present_fraud" and case.get("transaction_type") != "online_purchase":
            warnings.append("confirm that the fraud transaction was online/phone/card-not-present")
        if category == "card_present_fraud" and case.get("transaction_type") not in {"pin_purchase", "signature_purchase"}:
            warnings.append("confirm that the fraud transaction was card-present")
        if category == "atm_cash_discrepancy" and amount and amount > Decimal("200") and case.get("atm_owner") == "third_party":
            warnings.append("third-party ATM discrepancy over $200 requires EFT Error Resolution Affidavit")
        if category in {"card_present_fraud", "card_not_present_fraud"} and amount and amount > Decimal("500") and not case.get("police_report_filed"):
            warnings.append("recommend a police report for fraud over $500")

        group = case.get("duplicate_group")
        if category == "duplicate_charge" and group and duplicate_groups.get(group):
            dates = [(parse_date(x.get("transaction_date")), x.get("transaction_id")) for x in duplicate_groups[group]]
            dates = [(d, t) for d, t in dates if d]
            if dates and tid != min(dates)[1]:
                errors.append("duplicate disputes must use the earliest transaction in the duplicate group")

        pc, pc_reasons, pc_blockers = provisional(case, account or {}, as_of)
        errors.extend(pc_blockers)
        if account and str(account.get("tier", "")).lower() in LIMITS:
            limit = LIMITS[str(account.get("tier")).lower()]
            projected = existing_by_account.get(aid, 0) + planned_by_account.get(aid, 0) + 1
            if projected > limit:
                errors.append("filing would exceed the account's maximum open-dispute limit")

        action = ACTIONS.get(category)
        result = {"index": index, "transaction_id": tid, "errors": errors, "warnings": warnings,
                  "provisional_credit_eligible": pc, "provisional_credit_reasons": pc_reasons,
                  "card_action": action}
        if not errors:
            payload = {
                "transaction_id": tid, "account_id": aid, "card_id": cid, "user_id": uid,
                "dispute_category": category, "transaction_date": case.get("transaction_date"),
                "discovery_date": case.get("discovery_date"), "disputed_amount": float(amount),
                "transaction_type": case.get("transaction_type"), "card_in_possession": case.get("card_in_possession"),
                "pin_compromised": case.get("pin_compromised"), "contacted_merchant": case.get("contacted_merchant"),
                "police_report_filed": case.get("police_report_filed"),
                "written_statement_provided": case.get("written_statement_provided"),
                "provisional_credit_eligible": pc, "card_action": action,
            }
            filings.append(payload)
            planned_by_account[aid] = planned_by_account.get(aid, 0) + 1
            if SEVERITY[action] > SEVERITY.get(action_by_card.get(cid, "keep_active"), -1):
                action_by_card[cid] = action
            result["payload_ready"] = True
        else:
            result["payload_ready"] = False
        case_results.append(result)

    card_actions = []
    for card_id, action in action_by_card.items():
        note = "No additional card action." if action == "keep_active" else "Perform once only after successful filings for this card."
        card_actions.append({"card_id": card_id, "final_action": action, "note": note})
    return {"filings": filings, "case_results": case_results, "card_actions": card_actions}


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(source), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "filings": []}, separators=(",", ":")))
