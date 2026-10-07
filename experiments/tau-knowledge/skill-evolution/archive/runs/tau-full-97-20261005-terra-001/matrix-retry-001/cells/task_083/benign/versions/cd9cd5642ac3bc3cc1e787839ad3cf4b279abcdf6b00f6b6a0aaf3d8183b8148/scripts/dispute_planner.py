#!/usr/bin/env python3
"""Plan one debit-card dispute. Reads a JSON object from stdin; writes JSON to stdout."""
import datetime as dt
import json
import sys

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
TIER_LIMITS = {"entry tier": 2, "mid tier": 3, "premium tier": 4, "elite tier": 5}
OPEN_DISPUTE_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTIONS = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}


def value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else default


def parse_date(text):
    if not isinstance(text, str):
        return None
    try:
        return dt.datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        return None


def is_number(item):
    return isinstance(item, (int, float)) and not isinstance(item, bool)


def plan(data):
    account = value(data, "account", {})
    card = value(data, "card", {})
    txn = value(data, "transaction", {})
    case = value(data, "case", {})
    blockers, missing, notices = [], [], []

    def required(obj, key, label=None):
        item = value(obj, key)
        if item is None or item == "":
            missing.append(label or key)
        return item

    now = parse_date(required(data, "now_date"))
    txn_date = parse_date(required(txn, "date", "transaction.date"))
    discovery = parse_date(required(case, "discovery_date", "case.discovery_date"))
    user_id = required(data, "user_id")
    account_id = required(account, "account_id", "account.account_id")
    card_id = required(card, "card_id", "card.card_id")
    transaction_id = required(txn, "transaction_id", "transaction.transaction_id")
    category = required(case, "category")
    transaction_type = required(case, "transaction_type")
    amount = required(case, "disputed_amount")

    if value(data, "verified") is not True:
        blockers.append("Customer identity has not been verified and logged.")
    if str(value(account, "account_type", "")).lower() != "checking":
        blockers.append("The linked account is not a checking account.")
    if value(account, "status") != "OPEN":
        blockers.append("The linked checking account is not OPEN.")
    if value(card, "account_id") != account_id:
        blockers.append("The selected card is not linked to the selected checking account.")
    if value(card, "user_id") != user_id:
        blockers.append("The selected card is not owned by the verified user.")
    if value(txn, "account_id") != account_id:
        blockers.append("The selected transaction does not belong to the selected account.")

    if category not in CATEGORIES:
        blockers.append("Dispute category is missing or unsupported.")
    if transaction_type not in TRANSACTION_TYPES:
        blockers.append("Transaction type is missing or unsupported.")
    if value(case, "pin_compromised") not in PIN_VALUES:
        missing.append("case.pin_compromised (yes_shared, yes_observed, no, or unknown)")
    for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not isinstance(value(case, field), bool):
            missing.append("case." + field)

    if not is_number(amount):
        blockers.append("Disputed amount must be a numeric dollar amount.")
    elif amount < 1:
        blockers.append("Disputed amount must be at least $1.00.")
    posted_amount = value(txn, "amount")
    if is_number(posted_amount) and is_number(amount) and amount > abs(posted_amount):
        blockers.append("Disputed amount exceeds the posted transaction amount.")

    if not now:
        missing.append("valid now_date in MM/DD/YYYY")
    if not txn_date:
        blockers.append("Transaction date is missing or not MM/DD/YYYY.")
    elif now and (now - txn_date).days > 60:
        blockers.append("Transaction is more than 60 days old.")
    elif now and (now - txn_date).days < 0:
        blockers.append("Transaction date is in the future.")
    if not discovery:
        blockers.append("Discovery date is missing or not MM/DD/YYYY.")

    tier = str(value(account, "account_class", "")).lower()
    limit = TIER_LIMITS.get(tier)
    if limit is None:
        missing.append("recognized checking account tier")
    disputes = value(data, "existing_disputes", []) or []
    if not isinstance(disputes, list):
        blockers.append("Existing-dispute data must be a list.")
        disputes = []
    open_count = sum(
        1 for dispute in disputes
        if value(dispute, "account_id") == account_id and value(dispute, "status") in OPEN_DISPUTE_STATUSES
    )
    if limit is not None and open_count >= limit:
        blockers.append("This checking account has reached its maximum open-dispute limit (%d)." % limit)
    if any(value(dispute, "transaction_id") == transaction_id and value(dispute, "status") in OPEN_DISPUTE_STATUSES for dispute in disputes):
        blockers.append("An open dispute already exists for this transaction.")

    candidates = value(case, "duplicate_candidates", []) or []
    if category == "duplicate_charge" and isinstance(candidates, list):
        valid = [(parse_date(value(item, "date")), value(item, "transaction_id")) for item in candidates]
        valid = [(when, ident) for when, ident in valid if when and ident]
        if valid and transaction_id != min(valid, key=lambda entry: entry[0])[1]:
            blockers.append("For a duplicate set, the earliest transaction must be disputed first.")

    # Eligibility is separate from filing readiness. Unknown statement timing must not block filing.
    timely = value(case, "timely_reported_within_60_statement_days")
    holds = value(account, "has_holds_or_restrictions")
    opened = parse_date(value(account, "date_opened"))
    pc_reasons = []
    pc_unknown = False
    if timely not in (True, False):
        pc_unknown = True
        pc_reasons.append("statement-based timeliness has not been established")
    elif timely is False:
        pc_reasons.append("reporting was not timely relative to the statement")
    if holds not in (True, False):
        pc_unknown = True
        pc_reasons.append("account holds/restrictions status has not been established")
    elif holds is True or value(account, "status") != "OPEN":
        pc_reasons.append("account is not OPEN without holds or restrictions")
    if not opened:
        pc_unknown = True
        pc_reasons.append("account opening date has not been established")
    if category not in PC_CATEGORIES:
        pc_reasons.append("category is not eligible for required provisional credit")
    if value(case, "written_statement_provided") is False:
        pc_reasons.append("no written statement was provided")
    if category not in {"card_present_fraud", "card_not_present_fraud"} and value(case, "contacted_merchant") is False:
        pc_reasons.append("merchant was not contacted for a non-fraud dispute")
    if value(case, "pin_compromised") == "yes_shared":
        pc_reasons.append("PIN was voluntarily shared")
    if opened and now and (now - opened).days < 30 and category == "card_not_present_fraud":
        pc_reasons.append("new-account card-not-present exclusion")
    provisional = False if pc_unknown else not pc_reasons

    action = ACTIONS.get(category, "keep_active")
    if category in {"card_present_fraud", "card_not_present_fraud"} and is_number(amount) and amount > 500 and value(case, "police_report_filed") is False:
        notices.append("Recommend filing a police report because the suspected-fraud amount exceeds $500.")
    if category == "atm_cash_discrepancy" and value(case, "atm_owner") == "third_party" and is_number(amount) and amount > 200:
        notices.append("Third-party ATM affidavit required: email it to the registered address; it must be signed and returned within 10 business days, and false signing is a federal offense.")

    # Unknown facts used only for credit eligibility deliberately do not prevent filing.
    filing_missing = [item for item in missing if item not in {
        "valid now_date in MM/DD/YYYY", "recognized checking account tier"
    }]
    ready = not blockers and not filing_missing
    filing = None
    if ready:
        filing = {
            "transaction_id": transaction_id,
            "account_id": account_id,
            "card_id": card_id,
            "user_id": user_id,
            "dispute_category": category,
            "transaction_date": value(txn, "date"),
            "discovery_date": value(case, "discovery_date"),
            "disputed_amount": amount,
            "transaction_type": transaction_type,
            "card_in_possession": value(case, "card_in_possession"),
            "pin_compromised": value(case, "pin_compromised"),
            "contacted_merchant": value(case, "contacted_merchant"),
            "police_report_filed": value(case, "police_report_filed"),
            "written_statement_provided": value(case, "written_statement_provided"),
            "provisional_credit_eligible": provisional,
            "card_action": action,
        }
    return {
        "filing_ready": ready,
        "blockers": blockers,
        "missing_facts": sorted(set(missing)),
        "open_dispute_count": open_count,
        "open_dispute_limit": limit,
        "per_filing_card_action": action,
        "provisional_credit_eligible": provisional,
        "provisional_credit_reasons": pc_reasons,
        "notices": notices,
        "filing_arguments": filing,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(plan(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        sys.exit(1)
