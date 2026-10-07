#!/usr/bin/env python3
"""Validate normalized debit-card dispute facts and recommend non-executing actions.

Reads one JSON object from stdin and writes one JSON object to stdout.  It never
calls banking systems.  Dates accept MM/DD/YYYY or YYYY-MM-DD; emitted dates are
MM/DD/YYYY.  See SKILL.md for the complete input schema.
"""
import json
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
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
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
PC_CATEGORIES = FRAUD | {"unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def fmt_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else value


def tier_limit(value):
    text = str(value or "").lower()
    for tier, limit in LIMITS.items():
        if tier in text:
            return limit
    return None


def business_days_after(start, end):
    """Weekday count after start through end; public holidays are not supplied."""
    if not start or not end or end < start:
        return None
    count = 0
    day = start
    while day < end:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count += 1
    return count


def liability(statement, filed):
    if not statement or not filed:
        return {"determined": False, "maximum": None, "message": "Statement date is required to determine Regulation E exposure."}
    calendar_days = (filed - statement).days
    business = business_days_after(statement, filed)
    if calendar_days < 0:
        return {"determined": False, "maximum": None, "message": "Filing date precedes the supplied statement date."}
    if business <= 2:
        return {"determined": True, "maximum": 50.0, "tier": "within_2_business_days", "business_days": business}
    if calendar_days <= 60:
        return {"determined": True, "maximum": 500.0, "tier": "within_60_days", "calendar_days": calendar_days}
    return {"determined": True, "maximum": None, "tier": "after_60_days", "message": "Potentially unlimited liability."}


def is_nonfraud(category):
    return category not in FRAUD


def main(data):
    filing = parse_date(data.get("filing_date"))
    global_errors = []
    if not filing:
        global_errors.append("filing_date must be MM/DD/YYYY or YYYY-MM-DD")
    user_id = data.get("user_id")
    accounts = {x.get("account_id"): x for x in data.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in data.get("cards", []) if x.get("card_id")}
    existing = defaultdict(int)
    for dispute in data.get("open_disputes", []):
        if str(dispute.get("status", "")).upper() in OPEN_STATUSES:
            existing[dispute.get("account_id")] += 1

    raw_claims = data.get("claims", [])
    # Retain the earliest item in every explicitly marked duplicate group.
    winners = {}
    for index, claim in enumerate(raw_claims):
        group = claim.get("duplicate_group")
        if not group:
            continue
        d = parse_date(claim.get("transaction_date")) or date.max
        sequence = claim.get("duplicate_sequence")
        try:
            sequence = int(sequence)
        except (TypeError, ValueError):
            sequence = index
        key = (d, sequence, index)
        if group not in winners or key < winners[group][0]:
            winners[group] = (key, index)

    evaluated = []
    reservations = defaultdict(int)
    successful_by_card = defaultdict(list)
    for index, claim in enumerate(raw_claims):
        errors, warnings = [], []
        group = claim.get("duplicate_group")
        if group and winners[group][1] != index:
            evaluated.append({"index": index, "transaction_id": claim.get("transaction_id"), "selected_for_filing": False,
                              "errors": [], "warnings": ["Skipped: a prior transaction in this duplicate group must be disputed first."],
                              "filing_payload": None})
            continue

        category = claim.get("dispute_category")
        tx_type = claim.get("transaction_type")
        tx_date = parse_date(claim.get("transaction_date"))
        discovery = parse_date(claim.get("discovery_date"))
        statement = parse_date(claim.get("statement_date"))
        account = accounts.get(claim.get("account_id"))
        card = cards.get(claim.get("card_id"))
        if not claim.get("transaction_id"):
            errors.append("transaction_id is required from live transaction history")
        if category not in CATEGORIES:
            errors.append("dispute_category is invalid")
        if tx_type not in TYPES:
            errors.append("transaction_type is invalid")
        if not tx_date:
            errors.append("transaction_date is invalid")
        if not discovery:
            errors.append("discovery_date is invalid")
        if discovery and tx_date and discovery < tx_date:
            errors.append("discovery_date cannot precede transaction_date")
        try:
            transaction_amount = abs(float(claim.get("transaction_amount")))
            disputed_amount = float(claim.get("disputed_amount"))
            if disputed_amount < 1:
                errors.append("disputed_amount must be at least $1.00")
            if disputed_amount > transaction_amount:
                errors.append("disputed_amount cannot exceed the transaction amount")
        except (TypeError, ValueError):
            transaction_amount = disputed_amount = None
            errors.append("transaction_amount and disputed_amount must be numeric")
        if filing and tx_date and (filing - tx_date).days > 60:
            errors.append("transaction is more than 60 calendar days old")
        if filing and tx_date and tx_date > filing:
            errors.append("transaction_date cannot be after filing_date")
        if not account:
            errors.append("claimed account was not retrieved")
        else:
            if str(account.get("account_type", "")).lower() != "checking":
                errors.append("debit-card dispute requires a checking account")
            if str(account.get("status", "")).upper() != "OPEN":
                errors.append("linked checking account is not OPEN")
            if tier_limit(account.get("account_class")) is None:
                errors.append("account_class does not identify Entry, Mid, Premium, or Elite tier")
        if not card:
            errors.append("claimed debit card was not retrieved")
        else:
            if card.get("account_id") != claim.get("account_id"):
                errors.append("card is not linked to claimed account")
            if user_id and card.get("user_id") != user_id:
                errors.append("card does not belong to verified user")
        for bool_field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
            if not isinstance(claim.get(bool_field), bool):
                errors.append(bool_field + " must be boolean")
        if claim.get("pin_compromised") not in PINS:
            errors.append("pin_compromised is invalid")
        if category in FRAUD and claim.get("fraud_suspected") is False:
            errors.append("fraud category conflicts with fraud_suspected=false")
        if category == "unauthorized_transaction" and claim.get("fraud_suspected") is True:
            errors.append("suspected fraud must use a card-present or card-not-present fraud category")
        if category in FRAUD and disputed_amount and disputed_amount > 500 and not claim.get("police_report_filed"):
            warnings.append("Recommend a police report for suspected fraud over $500.")
        if category == "atm_cash_discrepancy" or category == "atm_deposit_not_credited":
            if claim.get("atm_owner") not in {"rho_bank", "third_party"}:
                warnings.append("Confirm whether the ATM was Rho-Bank or third-party before proceeding with its process.")

        exposure = liability(statement, filing)
        if not statement:
            warnings.append("Statement date is missing; timely-reporting and provisional-credit determination is not definitive.")
        account_clear = bool(account) and str(account.get("status", "")).upper() == "OPEN" and not bool(account.get("has_holds_or_restrictions"))
        account_opened = parse_date(account.get("date_opened")) if account else None
        new_account = bool(filing and account_opened and (filing - account_opened).days < 30)
        pc_reasons = []
        if category not in PC_CATEGORIES:
            pc_reasons.append("category is not a required-provisional-credit category")
        if not statement:
            pc_reasons.append("statement date is unavailable")
        elif not filing or (filing - statement).days > 60 or (filing - statement).days < 0:
            pc_reasons.append("reporting is not within 60 days of statement date")
        if not claim.get("written_statement_provided"):
            pc_reasons.append("written statement not provided")
        if not account_clear:
            pc_reasons.append("account is not OPEN and clear of holds/restrictions")
        if claim.get("pin_compromised") == "yes_shared":
            pc_reasons.append("PIN was voluntarily shared")
        if new_account and category == "card_not_present_fraud":
            pc_reasons.append("new-account card-not-present exclusion")
        if is_nonfraud(category) and not claim.get("contacted_merchant"):
            pc_reasons.append("merchant has not been contacted for non-fraud dispute")
        provisional = len(pc_reasons) == 0

        capacity_ok = False
        if account and tier_limit(account.get("account_class")) is not None:
            capacity_ok = existing[claim.get("account_id")] + reservations[claim.get("account_id")] < tier_limit(account.get("account_class"))
            if not capacity_ok:
                errors.append("account has reached its maximum open-dispute limit")
        eligible = not errors and capacity_ok
        payload = None
        if eligible:
            reservations[claim.get("account_id")] += 1
            payload = {
                "transaction_id": claim.get("transaction_id"), "account_id": claim.get("account_id"),
                "card_id": claim.get("card_id"), "user_id": user_id, "dispute_category": category,
                "transaction_date": fmt_date(claim.get("transaction_date")), "discovery_date": fmt_date(claim.get("discovery_date")),
                "disputed_amount": disputed_amount, "transaction_type": tx_type,
                "card_in_possession": claim.get("card_in_possession"), "pin_compromised": claim.get("pin_compromised"),
                "contacted_merchant": claim.get("contacted_merchant"), "police_report_filed": claim.get("police_report_filed"),
                "written_statement_provided": claim.get("written_statement_provided"),
                "provisional_credit_eligible": provisional, "card_action": ACTIONS.get(category),
            }
            successful_by_card[claim.get("card_id")].append(category)
        evaluated.append({
            "index": index, "transaction_id": claim.get("transaction_id"), "selected_for_filing": True,
            "eligible_to_file": eligible, "errors": errors, "warnings": warnings,
            "liability_exposure": exposure, "provisional_credit_eligible": provisional,
            "provisional_credit_reasons_not_required": pc_reasons,
            "provisional_credit_amount": disputed_amount if provisional else 0.0,
            "filing_payload": payload,
        })

    card_actions = []
    for card_id, categories in successful_by_card.items():
        action = max((ACTIONS[c] for c in categories), key=lambda x: SEVERITY[x])
        card = cards.get(card_id, {})
        blockers = []
        tool = None
        arguments = None
        if action == "freeze_pending_investigation":
            if str(card.get("status", "")).upper() != "ACTIVE":
                blockers.append("card must be ACTIVE to freeze")
            else:
                tool, arguments = "freeze_debit_card_3892", {"card_id": card_id}
        elif action == "close_and_reissue":
            if str(card.get("status", "")).upper() not in {"ACTIVE", "PENDING"}:
                blockers.append("card must be ACTIVE or PENDING to close")
            if card.get("pending_transactions"):
                blockers.append("pending transactions must settle before closure")
            if card.get("pending_refunds"):
                blockers.append("pending refunds require the closure procedure's written acknowledgement or settlement")
            if not blockers:
                tool, arguments = "close_debit_card_4721", {"card_id": card_id, "reason": "fraud_suspected"}
        card_actions.append({"card_id": card_id, "actual_action": action, "categories": categories,
                             "tool": tool, "arguments": arguments, "blockers": blockers})
    return {"global_errors": global_errors, "claims": evaluated, "card_actions": card_actions,
            "note": "Recommendations only. Verify live facts and execute banking tools separately."}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(request), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
