#!/usr/bin/env python3
"""Assess proposed debit-card dispute filings without banking side effects.

Input JSON schema (all dates are MM/DD/YYYY):
{
  "current_date": "...", "user_verified": true, "user_id": "...",
  "accounts": [{"account_id":"...", "account_type":"checking", "status":"OPEN",
                "account_class":"Entry|Mid|Premium|Elite", "date_opened":"...",
                "has_holds":false, "has_restrictions":false}],
  "cards": [{"card_id":"...", "account_id":"...", "user_id":"..."}],
  "transactions": [{"transaction_id":"...", "account_id":"...", "date":"...", "amount":-12.34}],
  "existing_disputes": [{"account_id":"...", "status":"OPEN"}],
  "proposed_disputes": [{
    "transaction_id":"...", "account_id":"...", "card_id":"...",
    "dispute_category":"...", "disputed_amount":12.34,
    "discovery_date":"...", "transaction_type":"...",
    "fraud_suspected":false, "card_in_possession":true,
    "pin_compromised":"no", "contacted_merchant":true,
    "police_report_filed":false, "written_statement_provided":true,
    "reported_within_60_days_of_statement":true,
    "liability_timing":"within_2_business_days|within_60_days|after_60_days",
    "atm_operator":"rho_bank|third_party", "duplicate_group":"optional group label"
  }]
}

`has_holds` and `has_restrictions` must be explicit booleans to establish account
standing. `reported_within_60_days_of_statement` is deliberately supplied rather
than inferred from discovery date because the statement date is required by policy.
For a duplicate group, the script selects the earliest transaction by transaction
date (and transaction ID as a stable tie-breaker) and blocks later candidates.

Output contains per-proposal eligibility/blockers/warnings, the category-derived
card action, and provisional-credit assessment. It does not call tools or write data.
"""
import json
import sys
from datetime import datetime, date
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
PIN_VALUES = {"yes_shared", "yes_observed", "no", "unknown"}
FRAUD_CATEGORIES = {"card_present_fraud", "card_not_present_fraud"}
PROVISIONAL_CATEGORIES = FRAUD_CATEGORIES | {
    "unauthorized_transaction", "atm_cash_discrepancy", "duplicate_charge"
}
NON_FRAUD_CATEGORIES = CATEGORIES - FRAUD_CATEGORIES
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
TIER_LIMITS = {"ENTRY": 2, "MID": 3, "PREMIUM": 4, "ELITE": 5}
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
LIABILITY = {
    "within_2_business_days": Decimal("50"),
    "within_60_days": Decimal("500"),
    "after_60_days": None,
}


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None


def money(value, label, errors):
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{label} must be a finite numeric value.")
        return None


def normalized_tier(value):
    return str(value or "").strip().upper().replace(" TIER", "")


def account_standing(account):
    # Unknown holds/restrictions cannot establish required provisional-credit standing.
    return account.get("status") == "OPEN" and account.get("has_holds") is False and account.get("has_restrictions") is False


def main(data):
    top_errors = []
    current = parse_date(data.get("current_date"), "current_date", top_errors)
    if not isinstance(data.get("user_verified"), bool):
        top_errors.append("user_verified must be boolean.")
    for field in ("accounts", "cards", "transactions", "existing_disputes", "proposed_disputes"):
        if not isinstance(data.get(field), list):
            top_errors.append(f"{field} must be an array.")
    if top_errors:
        return {"ok": False, "input_errors": top_errors, "assessments": []}

    user_id = data.get("user_id")
    accounts = {a.get("account_id"): a for a in data["accounts"] if a.get("account_id")}
    cards = {c.get("card_id"): c for c in data["cards"] if c.get("card_id")}
    transactions = {t.get("transaction_id"): t for t in data["transactions"] if t.get("transaction_id")}
    open_counts = {}
    for record in data["existing_disputes"]:
        if record.get("status") in OPEN_STATUSES and record.get("account_id"):
            aid = record["account_id"]
            open_counts[aid] = open_counts.get(aid, 0) + 1

    # Resolve duplicate-group priority before assessing capacity.
    first_in_group = {}
    for index, proposal in enumerate(data["proposed_disputes"]):
        group = proposal.get("duplicate_group")
        if not group:
            continue
        tx = transactions.get(proposal.get("transaction_id"), {})
        errors = []
        tx_date = parse_date(tx.get("date"), f"transaction date for proposal {index}", errors)
        key = (tx_date or date.max, str(proposal.get("transaction_id", "")))
        if group not in first_in_group or key < first_in_group[group][0]:
            first_in_group[group] = (key, index)

    assessments = []
    planned_counts = dict(open_counts)
    for index, p in enumerate(data["proposed_disputes"]):
        blockers, warnings = [], []
        category = p.get("dispute_category")
        action = ACTIONS.get(category)
        account = accounts.get(p.get("account_id"))
        card = cards.get(p.get("card_id"))
        tx = transactions.get(p.get("transaction_id"))

        if not data.get("user_verified"):
            blockers.append("Customer identity and authority have not been verified and logged.")
        if category not in CATEGORIES:
            blockers.append("Dispute category is not one of the permitted values.")
        if p.get("transaction_type") not in TRANSACTION_TYPES:
            blockers.append("Transaction type is not one of the permitted values.")
        if p.get("pin_compromised") not in PIN_VALUES:
            blockers.append("PIN compromise status is missing or invalid.")
        if not isinstance(p.get("card_in_possession"), bool):
            blockers.append("Card-in-possession answer must be boolean.")
        if not isinstance(p.get("written_statement_provided"), bool):
            blockers.append("Written-statement answer must be boolean.")
        if not isinstance(p.get("contacted_merchant"), bool):
            blockers.append("Merchant-contact answer must be boolean.")
        if not isinstance(p.get("fraud_suspected"), bool):
            blockers.append("Fraud-suspected answer must be boolean.")

        if not account:
            blockers.append("Selected account was not found in supplied account data.")
        else:
            if account.get("account_type") != "checking":
                blockers.append("Debit-card disputes require a checking account.")
            if account.get("status") != "OPEN":
                blockers.append("Linked checking account is not OPEN.")
        if not card:
            blockers.append("Selected debit card was not found in supplied card data.")
        else:
            if card.get("account_id") != p.get("account_id"):
                blockers.append("Debit card is not linked to the selected account.")
            if card.get("user_id") != user_id:
                blockers.append("Customer does not own the selected debit card.")
        if not tx:
            blockers.append("Requested transaction was not found in supplied transaction data.")
        else:
            if tx.get("account_id") != p.get("account_id"):
                blockers.append("Transaction does not belong to the selected account.")
            tx_errors = []
            tx_date = parse_date(tx.get("date"), "transaction date", tx_errors)
            blockers.extend(tx_errors)
            if current and tx_date:
                age = (current - tx_date).days
                if age < 0:
                    blockers.append("Transaction date is in the future.")
                elif age > 60:
                    blockers.append("Transaction is more than 60 days old.")
            tx_amount = money(tx.get("amount"), "transaction amount", blockers)
            if tx_amount is not None and abs(tx_amount) < Decimal("1"):
                blockers.append("Transaction amount is below $1.00.")
            if tx_amount is not None and tx_amount >= 0:
                blockers.append("Transaction is not a debit.")
            requested = money(p.get("disputed_amount"), "disputed_amount", blockers)
            if requested is not None:
                if requested <= 0:
                    blockers.append("Disputed amount must be greater than zero.")
                if tx_amount is not None and requested > abs(tx_amount):
                    blockers.append("Disputed amount exceeds the transaction debit amount.")

        discovery = parse_date(p.get("discovery_date"), "discovery_date", blockers)
        if current and discovery and discovery > current:
            blockers.append("Discovery date is in the future.")
        if tx and discovery:
            tx_date_errors = []
            tx_date = parse_date(tx.get("date"), "transaction date", tx_date_errors)
            if tx_date and discovery < tx_date:
                warnings.append("Discovery date precedes transaction date; verify the reported dates.")

        fraud = p.get("fraud_suspected")
        if category == "unauthorized_transaction" and fraud is True:
            blockers.append("Suspected fraud must use a card-present or card-not-present fraud category.")
        if category in FRAUD_CATEGORIES and fraud is not True:
            blockers.append("A fraud category requires confirmation that fraud is suspected.")
        if category in NON_FRAUD_CATEGORIES and category != "unauthorized_transaction" and fraud is True:
            warnings.append("Confirm that the selected non-fraud category accurately describes the issue.")
        if category in NON_FRAUD_CATEGORIES and p.get("contacted_merchant") is False:
            blockers.append("Merchant contact is required for a non-fraud dispute.")
        if category in {"atm_cash_discrepancy", "atm_deposit_not_credited"}:
            if p.get("atm_operator") not in {"rho_bank", "third_party"}:
                blockers.append("ATM operator must be identified as rho_bank or third_party.")
        if category == "duplicate_charge" and p.get("duplicate_group"):
            group_entry = first_in_group.get(p["duplicate_group"])
            if group_entry and group_entry[1] != index:
                blockers.append("Only the earliest transaction in a duplicate group may be filed.")

        tier = normalized_tier(account.get("account_class") if account else None)
        limit = TIER_LIMITS.get(tier)
        if not limit:
            blockers.append("Checking-account tier is missing or unsupported; open-dispute limit cannot be verified.")
        else:
            used = planned_counts.get(p.get("account_id"), 0)
            if used >= limit:
                blockers.append(f"Open-dispute limit reached for {tier.title()} tier ({limit}).")

        timely = p.get("reported_within_60_days_of_statement")
        liability_timing = p.get("liability_timing")
        if timely is not True and timely is not False:
            warnings.append("Statement-based 60-day reporting status is unknown; provisional credit cannot be required.")
        if liability_timing not in LIABILITY:
            warnings.append("Regulation E liability interval has not been recorded.")
        elif liability_timing == "after_60_days":
            warnings.append("Customer may have unlimited liability and may not recover funds after 60 days.")

        acct_open_date = None
        if account and account.get("date_opened"):
            date_errors = []
            acct_open_date = parse_date(account.get("date_opened"), "account date_opened", date_errors)
            warnings.extend(date_errors)
        new_account = bool(current and acct_open_date and (current - acct_open_date).days < 30)
        standing = bool(account and account_standing(account))
        if account and account.get("status") == "OPEN" and not standing:
            warnings.append("Account holds/restrictions are not explicitly clear; do not assert required provisional credit.")
        nonfraud_no_contact = category in NON_FRAUD_CATEGORIES and p.get("contacted_merchant") is False
        excluded = (
            category not in PROVISIONAL_CATEGORIES or
            nonfraud_no_contact or
            p.get("pin_compromised") == "yes_shared" or
            (new_account and category == "card_not_present_fraud")
        )
        provisional_required = bool(
            timely is True and category in PROVISIONAL_CATEGORIES and
            p.get("written_statement_provided") is True and standing and not excluded
        )
        if category in FRAUD_CATEGORIES and money(p.get("disputed_amount"), "disputed_amount", []) and money(p.get("disputed_amount"), "disputed_amount", []) > Decimal("500") and p.get("police_report_filed") is False:
            warnings.append("Recommend a police report for suspected fraud over $500.")

        if not blockers and limit:
            planned_counts[p.get("account_id")] = planned_counts.get(p.get("account_id"), 0) + 1

        liability_cap = LIABILITY.get(liability_timing)
        assessments.append({
            "proposal_index": index,
            "transaction_id": p.get("transaction_id"),
            "account_id": p.get("account_id"),
            "eligible_to_file": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "card_action": action,
            "provisional_credit_required": provisional_required,
            "provisional_credit_timeline_business_days": 20 if new_account else 10,
            "liability_maximum": None if liability_cap is None else float(liability_cap),
            "open_disputes_after_if_filed": planned_counts.get(p.get("account_id"), open_counts.get(p.get("account_id"), 0)),
        })
    return {"ok": True, "assessments": assessments}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON value must be an object.")
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "input_errors": [str(exc)], "assessments": []}))
