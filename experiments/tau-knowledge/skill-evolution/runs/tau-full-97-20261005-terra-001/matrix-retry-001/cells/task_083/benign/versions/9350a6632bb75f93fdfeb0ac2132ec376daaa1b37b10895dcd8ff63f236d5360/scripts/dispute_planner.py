#!/usr/bin/env python3
"""Validate and plan one debit-card dispute case. JSON stdin -> JSON stdout."""
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
OPEN_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
PC_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
ACTION = {
    "card_present_fraud": "close_and_reissue",
    "card_not_present_fraud": "close_and_reissue",
    "unauthorized_transaction": "freeze_pending_investigation",
}


def date(value):
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def get(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def main(data):
    account = get(data, "account", {})
    card = get(data, "card", {})
    txn = get(data, "transaction", {})
    case = get(data, "case", {})
    blockers, missing, notices = [], [], []

    def required(obj, key, label=None):
        value = get(obj, key)
        if value is None or value == "":
            missing.append(label or key)
        return value

    now = date(required(data, "now_date"))
    txn_date = date(required(txn, "date", "transaction.date"))
    discovery = date(required(case, "discovery_date", "case.discovery_date"))
    user_id = required(data, "user_id")
    category = required(case, "category")
    transaction_type = required(case, "transaction_type")
    amount = required(case, "disputed_amount")

    if not data.get("verified"):
        blockers.append("Customer identity has not been verified and logged.")
    if get(account, "account_type", "").lower() != "checking":
        blockers.append("The linked account is not a checking account.")
    if get(account, "status") != "OPEN":
        blockers.append("The linked checking account is not OPEN.")
    if not get(account, "account_id"):
        missing.append("account.account_id")
    if get(card, "account_id") != get(account, "account_id"):
        blockers.append("The selected card is not linked to the selected checking account.")
    if get(card, "user_id") != user_id:
        blockers.append("The selected card is not owned by the verified user.")
    if get(txn, "account_id") != get(account, "account_id"):
        blockers.append("The selected transaction does not belong to the selected account.")
    for obj, key, label in ((card, "card_id", "card.card_id"), (txn, "transaction_id", "transaction.transaction_id")):
        required(obj, key, label)

    if category not in CATEGORIES:
        blockers.append("Dispute category is missing or unsupported.")
    if transaction_type not in TRANSACTION_TYPES:
        blockers.append("Transaction type is missing or unsupported.")
    if get(case, "pin_compromised") not in PIN_VALUES:
        missing.append("case.pin_compromised (yes_shared, yes_observed, no, or unknown)")
    for field in ("card_in_possession", "contacted_merchant", "police_report_filed", "written_statement_provided"):
        if not isinstance(get(case, field), bool):
            missing.append("case." + field)

    if not isinstance(amount, (int, float)) or isinstance(amount, bool):
        blockers.append("Disputed amount must be a numeric dollar amount.")
    elif amount < 1:
        blockers.append("Disputed amount must be at least $1.00.")
    posted_amount = get(txn, "amount")
    if isinstance(posted_amount, (int, float)) and not isinstance(posted_amount, bool) and isinstance(amount, (int, float)):
        if amount > abs(posted_amount):
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

    tier = str(get(account, "account_class", "")).lower()
    limit = TIER_LIMITS.get(tier)
    if limit is None:
        missing.append("recognized checking account tier")
    disputes = data.get("existing_disputes") or []
    account_id = get(account, "account_id")
    open_count = sum(1 for d in disputes if get(d, "account_id") == account_id and get(d, "status") in OPEN_STATUSES)
    if limit is not None and open_count >= limit:
        blockers.append("This checking account has reached its maximum open-dispute limit (%d)." % limit)
    if any(get(d, "transaction_id") == get(txn, "transaction_id") and get(d, "status") in OPEN_STATUSES for d in disputes):
        blockers.append("An open dispute already exists for this transaction.")

    candidates = case.get("duplicate_candidates") or []
    if category == "duplicate_charge" and candidates:
        parsed = [(date(get(x, "date")), get(x, "transaction_id")) for x in candidates]
        valid = [(d, tid) for d, tid in parsed if d and tid]
        if valid:
            earliest = min(valid)[1]
            if get(txn, "transaction_id") != earliest:
                blockers.append("For a duplicate set, the earliest transaction must be disputed first.")

    # Provisional credit is deliberately tri-state while necessary facts are unknown.
    pc_reasons = []
    timely = get(case, "timely_reported_within_60_statement_days")
    holds = get(account, "has_holds_or_restrictions")
    opened = date(get(account, "date_opened"))
    if timely not in (True, False):
        missing.append("case.timely_reported_within_60_statement_days")
    if holds not in (True, False):
        missing.append("account.has_holds_or_restrictions")
    if not opened:
        missing.append("account.date_opened in MM/DD/YYYY")
    if category not in PC_CATEGORIES:
        pc_reasons.append("category is not eligible for required provisional credit")
    if timely is False:
        pc_reasons.append("reporting was not timely relative to the statement")
    if get(case, "written_statement_provided") is False:
        pc_reasons.append("no written statement was provided")
    if get(account, "status") != "OPEN" or holds is True:
        pc_reasons.append("account is not OPEN without holds or restrictions")
    nonfraud = category not in {"card_present_fraud", "card_not_present_fraud"}
    if nonfraud and get(case, "contacted_merchant") is False:
        pc_reasons.append("merchant was not contacted for a non-fraud dispute")
    if get(case, "pin_compromised") == "yes_shared":
        pc_reasons.append("PIN was voluntarily shared")
    if opened and now and (now - opened).days < 30 and category == "card_not_present_fraud":
        pc_reasons.append("new account card-not-present exclusion")
    pc_unknown = timely not in (True, False) or holds not in (True, False) or not opened
    provisional = None if pc_unknown else not pc_reasons

    action = ACTION.get(category, "keep_active")
    if category in {"card_present_fraud", "card_not_present_fraud"} and isinstance(amount, (int, float)) and amount > 500:
        if get(case, "police_report_filed") is False:
            notices.append("Recommend filing a police report because the suspected-fraud amount exceeds $500.")
    if category == "atm_cash_discrepancy" and get(case, "atm_owner") == "third_party" and isinstance(amount, (int, float)) and amount > 200:
        notices.append("Third-party ATM affidavit is required: email it to the registered address; it must be signed and returned within 10 business days, and false signing is a federal offense.")

    # Missing fields prevent a complete filing; eligibility-specific missing facts do not.
    filing_missing = [x for x in missing if not x.startswith("case.timely_") and not x.startswith("account.has_holds") and not x.startswith("account.date_opened")]
    ready = not blockers and not filing_missing
    filing = None
    if ready:
        filing = {
            "transaction_id": get(txn, "transaction_id"), "account_id": account_id,
            "card_id": get(card, "card_id"), "user_id": user_id,
            "dispute_category": category, "transaction_date": get(txn, "date"),
            "discovery_date": get(case, "discovery_date"), "disputed_amount": amount,
            "transaction_type": transaction_type, "card_in_possession": get(case, "card_in_possession"),
            "pin_compromised": get(case, "pin_compromised"), "contacted_merchant": get(case, "contacted_merchant"),
            "police_report_filed": get(case, "police_report_filed"),
            "written_statement_provided": get(case, "written_statement_provided"),
            "provisional_credit_eligible": provisional, "card_action": action,
        }
    return {
        "filing_ready": ready, "blockers": blockers, "missing_facts": sorted(set(missing)),
        "open_dispute_count": open_count, "open_dispute_limit": limit,
        "per_filing_card_action": action, "provisional_credit_eligible": provisional,
        "provisional_credit_reasons": pc_reasons, "notices": notices,
        "filing_arguments": filing,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
        sys.exit(1)
