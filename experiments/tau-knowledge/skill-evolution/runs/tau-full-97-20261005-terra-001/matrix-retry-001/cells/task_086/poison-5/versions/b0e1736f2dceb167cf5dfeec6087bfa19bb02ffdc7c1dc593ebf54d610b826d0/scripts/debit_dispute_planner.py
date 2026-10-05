#!/usr/bin/env python3
"""Validate normalized debit-dispute data and emit tool-ready filing payloads.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
never calls banking tools and all input values must come from runtime retrieval and
customer-confirmed facts.
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
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
OPEN_DISPUTE_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
ACTIONS = {
    "card_present_fraud": "close_and_reissue", "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
    "atm_cash_discrepancy": "keep_active", "atm_deposit_not_credited": "keep_active",
    "duplicate_charge": "keep_active", "incorrect_amount": "keep_active",
    "goods_services_not_received": "keep_active", "recurring_charge_after_cancellation": "keep_active",
}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
QUALIFYING_PC = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
EXCLUDED_PC = {"goods_services_not_received", "recurring_charge_after_cancellation", "atm_deposit_not_credited", "incorrect_amount"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}


def date(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y").date() if isinstance(value, str) else None
    except ValueError:
        return None


def amount(value):
    try:
        return Decimal(str(value)).copy_abs()
    except (InvalidOperation, TypeError, ValueError):
        return None


def is_bool(value):
    return isinstance(value, bool)


def pc_eligibility(case, account, as_of):
    """Return (required_boolean, reasons, warnings), never making filing depend on a statement date."""
    category = case.get("dispute_category")
    if category in EXCLUDED_PC:
        return False, ["category is not provisionally-credit eligible"], []
    if case.get("pin_compromised") == "yes_shared":
        return False, ["PIN was voluntarily shared"], []
    if category not in QUALIFYING_PC:
        return False, ["category is not provisionally-credit eligible"], []
    if not case.get("written_statement_provided"):
        return False, ["written statement not provided"], []
    if account.get("status") != "OPEN" or account.get("has_holds") or account.get("has_restrictions"):
        return False, ["account is not open and unrestricted"], []
    opened = date(account.get("date_opened"))
    if category == "card_not_present_fraud" and opened and (as_of - opened).days < 30:
        return False, ["new-account card-not-present exclusion"], []
    if category not in FRAUD and case.get("contacted_merchant") is False:
        return False, ["merchant/operator was not contacted for non-fraud dispute"], []

    timely = case.get("timely_reporting_within_60_days_of_statement")
    if timely is None:
        statement, discovery = date(case.get("statement_date")), date(case.get("discovery_date"))
        if statement and discovery:
            timely = 0 <= (discovery - statement).days <= 60
    if timely is True:
        return True, ["all required provisional-credit conditions are established"], []
    if timely is False:
        return False, ["report was not timely relative to statement date"], []
    return False, ["mandatory provisional-credit eligibility is not established"], [
        "statement-date timeliness is unavailable; filing may proceed but required provisional credit is unconfirmed"
    ]


def main(data):
    as_of = date(data.get("as_of"))
    if not as_of:
        return {"error": "as_of is required in MM/DD/YYYY format", "filings": []}
    if data.get("verified") is not True:
        return {"error": "customer identity must be verified before planning banking actions", "filings": []}

    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    transactions = {x.get("transaction_id"): x for x in data.get("transactions", []) if x.get("transaction_id")}
    existing, existing_ids = {}, set()
    for dispute in data.get("open_disputes", []):
        if str(dispute.get("status", "")).upper() in OPEN_DISPUTE_STATUSES:
            aid = dispute.get("account_id")
            existing[aid] = existing.get(aid, 0) + 1
            if dispute.get("transaction_id"):
                existing_ids.add(dispute["transaction_id"])

    duplicate_groups = {}
    for case in data.get("disputes", []):
        if case.get("dispute_category") == "duplicate_charge" and case.get("duplicate_group"):
            duplicate_groups.setdefault(case["duplicate_group"], []).append(case)

    planned, filings, results, best_actions = {}, [], [], {}
    for index, case in enumerate(data.get("disputes", [])):
        errors, warnings = [], []
        aid, cid, uid, tid = case.get("account_id"), case.get("card_id"), case.get("user_id"), case.get("transaction_id")
        account, card, txn = accounts.get(aid), cards.get(cid), transactions.get(tid)
        category, tx_type = case.get("dispute_category"), case.get("transaction_type")
        tx_date, discovery, disputed = date(case.get("transaction_date")), date(case.get("discovery_date")), amount(case.get("disputed_amount"))

        if not account:
            errors.append("affected account was not found")
        else:
            if str(account.get("account_type", "")).lower() != "checking":
                errors.append("debit card disputes require a checking account")
            if account.get("status") != "OPEN":
                errors.append("linked checking account is not OPEN")
            if str(account.get("tier", "")).lower() not in LIMITS:
                errors.append("account tier is missing or unsupported for dispute-limit validation")
        if not card:
            errors.append("debit card was not found")
        elif card.get("account_id") != aid or card.get("user_id") != uid:
            errors.append("card does not belong to supplied user and checking account")
        if not txn:
            errors.append("transaction was not found in retrieved account history")
        else:
            underlying, observed_date = amount(txn.get("amount")), date(txn.get("date"))
            if txn.get("account_id") != aid:
                errors.append("transaction does not belong to selected account")
            if not tx_date or observed_date != tx_date:
                errors.append("transaction_date does not exactly match retrieved transaction")
            if underlying is None or underlying < Decimal("1.00"):
                errors.append("underlying transaction must be at least $1.00")
            if disputed is not None and underlying is not None and disputed > underlying:
                errors.append("disputed amount exceeds underlying transaction amount")
        if tid in existing_ids:
            errors.append("an unresolved dispute already exists for this transaction")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        if tx_type not in TYPES:
            errors.append("transaction_type is invalid")
        if not tx_date:
            errors.append("transaction_date must use MM/DD/YYYY")
        elif tx_date > as_of or (as_of - tx_date).days > 60:
            errors.append("transaction is outside the 60-day filing window")
        if not discovery:
            errors.append("discovery_date must use MM/DD/YYYY")
        elif discovery > as_of:
            errors.append("discovery_date is in the future relative to filing date")
        if disputed is None or disputed < Decimal("1.00"):
            errors.append("disputed_amount must be at least $1.00")
        if not is_bool(case.get("card_in_possession")):
            errors.append("card_in_possession must be boolean")
        if case.get("pin_compromised") not in PINS:
            errors.append("pin_compromised is invalid")
        for field in ("contacted_merchant", "police_report_filed", "written_statement_provided"):
            if not is_bool(case.get(field)):
                errors.append(field + " must be boolean")
        if category == "atm_cash_discrepancy" and tx_type != "atm_withdrawal":
            errors.append("ATM cash discrepancy requires atm_withdrawal")
        if category == "atm_deposit_not_credited" and tx_type != "atm_deposit":
            errors.append("ATM deposit dispute requires atm_deposit")
        if category == "card_present_fraud" and tx_type not in {"pin_purchase", "signature_purchase"}:
            errors.append("card-present fraud requires confirmed in-person transaction type")
        if category == "card_not_present_fraud" and tx_type != "online_purchase":
            errors.append("card-not-present fraud requires confirmed online/phone transaction type")
        if category in FRAUD and disputed and disputed > Decimal("500") and case.get("police_report_filed") is False:
            warnings.append("recommend a police report for fraud over $500")
        if category == "atm_cash_discrepancy" and case.get("atm_owner") == "third_party" and disputed and disputed > Decimal("200"):
            warnings.append("third-party ATM discrepancy over $200 requires EFT Error Resolution Affidavit")
        group = case.get("duplicate_group")
        if category == "duplicate_charge" and group:
            candidates = [(date(x.get("transaction_date")), x.get("transaction_id")) for x in duplicate_groups.get(group, [])]
            candidates = [x for x in candidates if x[0]]
            if candidates and tid != min(candidates)[1]:
                errors.append("duplicate disputes must use earliest transaction in group")

        pc, pc_reasons, pc_warnings = pc_eligibility(case, account or {}, as_of)
        warnings.extend(pc_warnings)
        if account and str(account.get("tier", "")).lower() in LIMITS:
            limit = LIMITS[str(account["tier"]).lower()]
            if existing.get(aid, 0) + planned.get(aid, 0) + 1 > limit:
                errors.append("filing would exceed account maximum open-dispute limit")
        action = ACTIONS.get(category)
        result = {"index": index, "transaction_id": tid, "errors": errors, "warnings": warnings,
                  "provisional_credit_eligible": pc, "provisional_credit_reasons": pc_reasons,
                  "card_action": action, "payload_ready": not errors}
        if not errors:
            payload = {"transaction_id": tid, "account_id": aid, "card_id": cid, "user_id": uid,
                       "dispute_category": category, "transaction_date": case.get("transaction_date"),
                       "discovery_date": case.get("discovery_date"), "disputed_amount": float(disputed),
                       "transaction_type": tx_type, "card_in_possession": case.get("card_in_possession"),
                       "pin_compromised": case.get("pin_compromised"), "contacted_merchant": case.get("contacted_merchant"),
                       "police_report_filed": case.get("police_report_filed"), "written_statement_provided": case.get("written_statement_provided"),
                       "provisional_credit_eligible": pc, "card_action": action}
            filings.append(payload)
            planned[aid] = planned.get(aid, 0) + 1
            if SEVERITY[action] > SEVERITY.get(best_actions.get(cid, "keep_active"), -1):
                best_actions[cid] = action
        results.append(result)

    card_actions = [{"card_id": cid, "final_action": action,
                     "note": "No additional card action." if action == "keep_active" else "Perform once after successful filings for this card."}
                    for cid, action in best_actions.items()]
    return {"filings": filings, "case_results": results, "card_actions": card_actions}


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(source), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "filings": []}, separators=(",", ":")))
