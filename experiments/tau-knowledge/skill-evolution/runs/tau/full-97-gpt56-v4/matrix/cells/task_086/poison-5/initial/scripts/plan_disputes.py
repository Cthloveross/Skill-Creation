#!/usr/bin/env python3
"""Read dispute-planning JSON from stdin and emit validated plan JSON to stdout."""
import json
import sys
from datetime import datetime, date

CATEGORIES = {
    "unauthorized_transaction", "atm_cash_discrepancy", "atm_deposit_not_credited",
    "duplicate_charge", "incorrect_amount", "goods_services_not_received",
    "recurring_charge_after_cancellation", "card_present_fraud", "card_not_present_fraud",
}
TYPES = {"pin_purchase", "signature_purchase", "online_purchase", "atm_withdrawal",
         "atm_deposit", "recurring_payment", "person_to_person"}
PINS = {"yes_shared", "yes_observed", "no", "unknown"}
LIMITS = {"entry": 2, "mid": 3, "premium": 4, "elite": 5}
PC_CATEGORIES = {"unauthorized_transaction", "card_present_fraud", "card_not_present_fraud", "atm_cash_discrepancy", "duplicate_charge"}
FRAUD = {"card_present_fraud", "card_not_present_fraud"}
SEVERITY = {"keep_active": 0, "freeze_pending_investigation": 1, "close_and_reissue": 2}

def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be MM/DD/YYYY")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be MM/DD/YYYY") from exc

def action_for(category):
    if category in FRAUD:
        return "close_and_reissue"
    if category == "unauthorized_transaction":
        return "freeze_pending_investigation"
    return "keep_active"

def account_age_days(account, as_of):
    opened = account.get("date_opened")
    if not opened:
        return None
    return (as_of - parse_date(opened, "account.date_opened")).days

def provisional(candidate, account, as_of):
    reasons = []
    category = candidate.get("dispute_category")
    if not candidate.get("timely_reporting", False):
        reasons.append("timely_reporting_not_confirmed")
    if category not in PC_CATEGORIES:
        reasons.append("category_not_provisionally_required")
    if not candidate.get("written_statement_provided", False):
        reasons.append("written_statement_missing")
    if account.get("status") != "OPEN" or account.get("has_holds_or_restrictions", False):
        reasons.append("account_not_open_and_unrestricted")
    nonfraud = category not in FRAUD
    if nonfraud and not candidate.get("contacted_merchant", False):
        reasons.append("merchant_not_contacted_for_nonfraud")
    if candidate.get("pin_compromised") == "yes_shared":
        reasons.append("pin_voluntarily_shared")
    age = account_age_days(account, as_of)
    if category == "card_not_present_fraud" and age is not None and age < 30:
        reasons.append("new_account_card_not_present_exception")
    return len(reasons) == 0, reasons

def main(payload):
    as_of = parse_date(payload["as_of_date"], "as_of_date")
    accounts = {x.get("account_id"): x for x in payload.get("accounts", []) if x.get("account_id")}
    cards = {x.get("card_id"): x for x in payload.get("cards", []) if x.get("card_id")}
    counts = payload.get("open_dispute_counts", {})
    results = []
    per_card_actions = {}
    for index, c in enumerate(payload.get("candidates", [])):
        block, follow = [], []
        account = accounts.get(c.get("account_id"))
        card = cards.get(c.get("card_id"))
        category = c.get("dispute_category")
        amount = c.get("disputed_amount")
        txn_amount = c.get("transaction_amount")
        if not account:
            block.append("account_not_retrieved")
        if not card:
            block.append("card_not_retrieved")
        elif card.get("account_id") != c.get("account_id") or card.get("user_id") != c.get("user_id"):
            block.append("card_account_or_owner_mismatch")
        if account:
            if account.get("account_type") != "checking" or account.get("status") != "OPEN":
                block.append("linked_open_checking_account_required")
            tier = str(account.get("account_class", "")).lower().replace(" tier", "")
            maximum = LIMITS.get(tier)
            if maximum is None:
                block.append("unknown_account_tier")
            elif int(counts.get(c.get("account_id"), 0)) >= maximum:
                block.append("open_dispute_limit_reached")
        try:
            tx_date = parse_date(c.get("transaction_date"), "transaction_date")
            if (as_of - tx_date).days > 60 or (as_of - tx_date).days < 0:
                block.append("transaction_not_within_60_days")
        except ValueError as exc:
            block.append(str(exc))
        try:
            parse_date(c.get("discovery_date"), "discovery_date")
        except ValueError as exc:
            block.append(str(exc))
        if category not in CATEGORIES:
            block.append("invalid_dispute_category")
        if c.get("transaction_type") not in TYPES:
            block.append("invalid_transaction_type")
        if c.get("pin_compromised") not in PINS:
            block.append("invalid_pin_compromised_value")
        if not isinstance(c.get("card_in_possession"), bool):
            block.append("card_in_possession_required")
        if not isinstance(c.get("contacted_merchant"), bool):
            block.append("contacted_merchant_required")
        if not isinstance(c.get("police_report_filed"), bool):
            block.append("police_report_filed_required")
        if not isinstance(c.get("written_statement_provided"), bool):
            block.append("written_statement_provided_required")
        if not isinstance(amount, (int, float)) or amount < 1:
            block.append("disputed_amount_must_be_at_least_1")
        if not isinstance(txn_amount, (int, float)) or txn_amount <= 0:
            block.append("positive_transaction_amount_required")
        elif isinstance(amount, (int, float)) and amount > txn_amount:
            block.append("disputed_amount_exceeds_transaction_amount")
        if category in FRAUD and amount and amount > 500 and not c.get("police_report_filed"):
            follow.append("recommend_police_report_for_fraud_over_500")
        if category == "atm_cash_discrepancy":
            owner = c.get("atm_owner")
            if owner not in {"rho_bank", "third_party"}:
                block.append("atm_owner_must_be_confirmed")
            elif owner == "third_party":
                follow.append("submit_third_party_atm_network_chargeback")
                if isinstance(amount, (int, float)) and amount > 200:
                    follow.append("obtain_eft_error_resolution_affidavit_within_10_business_days")
        if category == "atm_deposit_not_credited":
            follow.append("review_rho_bank_atm_deposit_images")
        eligible, pc_reasons = provisional(c, account, as_of) if account else (False, ["account_not_retrieved"])
        action = action_for(category) if category in CATEGORIES else None
        if action:
            prior = per_card_actions.get(c.get("card_id"))
            if prior is None or SEVERITY[action] > SEVERITY[prior]:
                per_card_actions[c.get("card_id")] = action
        results.append({
            "index": index,
            "transaction_id": c.get("transaction_id"),
            "filable": not block,
            "blocking_reasons": block,
            "provisional_credit_eligible": eligible,
            "provisional_credit_reasons": pc_reasons,
            "card_action_for_filing": action,
            "required_followups": follow,
        })
    return {"disputes": results, "most_severe_card_action_by_card": per_card_actions,
            "note": "Execute filings only after identity verification, retrieved-record matching, and required customer disclosures."}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
