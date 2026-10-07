#!/usr/bin/env python3
"""Validate and plan debit-card dispute filings. Reads one JSON object from stdin."""
import json
import sys
from datetime import datetime

CATEGORIES = {"unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited", "duplicate_charge", "incorrect_amount", "goods_services_not_received", "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud"}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal", "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {"unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge", "card_present_fraud", "card_not_present_fraud"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}
WINDOWS = {"within_2_business_days": 50.0, "within_60_days": 500.0, "after_60_days": -1.0}

def d(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}_must_be_MM/DD/YYYY")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError as exc:
        raise ValueError(f"{label}_must_be_MM/DD/YYYY") from exc

def action(category):
    return "close_and_reissue" if category in FRAUD else "freeze_pending_investigation" if category == "unauthorized_transaction" else "keep_active"

def bool_field(obj, field, problems):
    if not isinstance(obj.get(field), bool):
        problems.append(field + "_required")

def initial_counts(payload):
    supplied = payload.get("open_dispute_counts")
    if isinstance(supplied, dict):
        return {str(k): int(v) for k, v in supplied.items()}
    counts = {}
    for dispute in payload.get("existing_disputes", []):
        if dispute.get("status") in OPEN_STATUSES and dispute.get("account_id"):
            account_id = dispute["account_id"]
            counts[account_id] = counts.get(account_id, 0) + 1
    return counts

def liability(candidate, problems):
    window = candidate.get("liability_window")
    if window not in WINDOWS:
        problems.append("liability_window_not_confirmed")
        return None
    if window == "after_60_days":
        return -1.0
    amount = candidate.get("disputed_amount")
    return min(float(amount), WINDOWS[window]) if isinstance(amount, (int, float)) else None

def provisional(candidate, account, as_of):
    reasons = []
    cat = candidate.get("dispute_category")
    if candidate.get("timely_reporting") is not True:
        reasons.append("timely_reporting_not_confirmed")
    if cat not in PC_CATEGORIES:
        reasons.append("category_not_provisionally_required")
    if candidate.get("written_statement_provided") is not True:
        reasons.append("written_statement_missing")
    if account.get("status") != "OPEN" or account.get("has_holds_or_restrictions") is not False:
        reasons.append("account_not_confirmed_open_unrestricted")
    if cat not in FRAUD and candidate.get("contacted_merchant") is not True:
        reasons.append("merchant_not_contacted_for_nonfraud")
    if candidate.get("pin_compromised") == "yes_shared":
        reasons.append("pin_voluntarily_shared")
    try:
        age = (as_of - d(account.get("date_opened"), "account_date_opened")).days
        if cat == "card_not_present_fraud" and age < 30:
            reasons.append("new_account_card_not_present_exception")
    except ValueError:
        reasons.append("account_age_not_confirmed")
    return not reasons, reasons

def main(payload):
    as_of = d(payload["as_of_date"], "as_of_date")
    accounts = {a.get("account_id"): a for a in payload.get("accounts", []) if a.get("account_id")}
    cards = {c.get("card_id"): c for c in payload.get("cards", []) if c.get("card_id")}
    txns = {t.get("transaction_id"): t for t in payload.get("transactions", []) if t.get("transaction_id")}
    counts = initial_counts(payload)
    earliest = {}
    for candidate_index, candidate in enumerate(payload.get("candidates", [])):
        group = candidate.get("reported_duplicate_group")
        if group:
            try:
                value = (d(candidate.get("transaction_date"), "transaction_date"), candidate_index)
                earliest[group] = min(earliest.get(group, value), value)
            except ValueError:
                pass
    results, per_card = [], {}
    for i, c in enumerate(payload.get("candidates", [])):
        problems, followups = [], []
        account, card, txn = accounts.get(c.get("account_id")), cards.get(c.get("card_id")), txns.get(c.get("transaction_id"))
        cat, typ, amount = c.get("dispute_category"), c.get("transaction_type"), c.get("disputed_amount")
        if not account: problems.append("account_not_retrieved")
        if not card: problems.append("card_not_retrieved")
        elif card.get("account_id") != c.get("account_id") or card.get("user_id") != c.get("user_id"): problems.append("card_account_or_owner_mismatch")
        if not txn: problems.append("transaction_not_retrieved")
        else:
            if txn.get("account_id") != c.get("account_id"): problems.append("transaction_account_mismatch")
            if not isinstance(txn.get("amount"), (int, float)) or txn["amount"] > -1: problems.append("matched_transaction_must_be_debit_at_least_1")
            if txn.get("date") != c.get("transaction_date"): problems.append("transaction_date_does_not_match_record")
        if account:
            account_type = account.get("account_type", account.get("class"))
            if account_type != "checking" or account.get("status") != "OPEN": problems.append("linked_open_checking_account_required")
            tier = str(account.get("tier", account.get("account_class", ""))).strip().lower()
            if tier not in LIMITS: problems.append("confirmed_documented_tier_required")
            elif counts.get(c.get("account_id"), 0) >= LIMITS[tier]: problems.append("open_dispute_limit_reached")
        try:
            tx_date, discovery = d(c.get("transaction_date"), "transaction_date"), d(c.get("discovery_date"), "discovery_date")
            if not 0 <= (as_of - tx_date).days <= 60: problems.append("transaction_not_within_60_days")
            if discovery < tx_date or discovery > as_of: problems.append("discovery_date_invalid_for_filing_date")
        except ValueError as exc: problems.append(str(exc))
        if cat not in CATEGORIES: problems.append("invalid_dispute_category")
        if typ not in TYPES: problems.append("invalid_transaction_type")
        if cat == "card_present_fraud" and typ not in {"pin_purchase", "signature_purchase"}: problems.append("card_present_fraud_requires_physical_transaction_type")
        if cat == "card_not_present_fraud" and typ != "online_purchase": problems.append("card_not_present_fraud_requires_online_purchase")
        if c.get("pin_compromised") not in PINS: problems.append("invalid_pin_compromised_value")
        for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
            bool_field(c, field, problems)
        if not isinstance(amount, (int, float)) or amount < 1: problems.append("disputed_amount_must_be_at_least_1")
        if txn and isinstance(amount, (int, float)) and isinstance(txn.get("amount"), (int, float)) and amount > abs(txn["amount"]): problems.append("disputed_amount_exceeds_matched_transaction")
        group = c.get("reported_duplicate_group")
        if group:
            try:
                if (d(c.get("transaction_date"), "transaction_date"), i) != earliest.get(group): problems.append("only_earliest_duplicate_may_be_disputed")
            except ValueError: pass
        if cat == "atm_cash_discrepancy":
            owner = c.get("atm_owner")
            if owner not in {"rho_bank", "third_party"}: problems.append("atm_owner_must_be_confirmed")
            elif owner == "third_party":
                followups.append("submit_third_party_atm_network_chargeback")
                if isinstance(amount, (int, float)) and amount > 200: followups.append("obtain_eft_error_resolution_affidavit_within_10_business_days")
        if cat == "atm_deposit_not_credited": followups.append("review_rho_bank_atm_deposit_images_or_journal")
        if cat in FRAUD and isinstance(amount, (int, float)) and amount > 500 and c.get("police_report_filed") is False: followups.append("recommend_police_report_for_fraud_over_500")
        maximum_liability = liability(c, problems)
        pc_ok, pc_reasons = provisional(c, account, as_of) if account else (False, ["account_not_retrieved"])
        individual_action = action(cat) if cat in CATEGORIES else None
        filable = not problems
        if filable:
            counts[c["account_id"]] = counts.get(c["account_id"], 0) + 1
            old = per_card.get(c["card_id"])
            if old is None or SEVERITY[individual_action] > SEVERITY[old]: per_card[c["card_id"]] = individual_action
        payload_out = None
        if filable:
            keys = ("transaction_id", "account_id", "card_id", "user_id", "dispute_category", "transaction_date", "discovery_date", "disputed_amount", "transaction_type", "card_in_possession", "pin_compromised", "contacted_merchant", "police_report_filed", "written_statement_provided")
            payload_out = {k: c[k] for k in keys}
            payload_out.update({"provisional_credit_eligible": pc_ok, "customer_max_liability_amount": maximum_liability, "card_action": individual_action})
        results.append({"index": i, "transaction_id": c.get("transaction_id"), "filable": filable, "blocking_reasons": problems, "provisional_credit_eligible": pc_ok, "provisional_credit_reasons": pc_reasons, "customer_max_liability_amount": maximum_liability, "card_action_for_filing": individual_action, "required_followups": followups, "filing_payload": payload_out})
    return {"disputes": results, "open_dispute_counts_after_planned_filings": counts, "most_severe_card_action_by_card": per_card, "note": "Plans are advisory only; verify live records and complete disclosures before acting."}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        sys.exit(2)
