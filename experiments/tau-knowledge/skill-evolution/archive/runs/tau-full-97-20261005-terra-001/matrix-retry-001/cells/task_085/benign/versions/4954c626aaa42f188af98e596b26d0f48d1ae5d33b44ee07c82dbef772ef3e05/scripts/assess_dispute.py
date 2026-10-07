#!/usr/bin/env python3
"""Assess an ATM cash-discrepancy dispute from runtime-supplied JSON facts.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper has
no banking, network, or filesystem side effects. Missing statement timing never blocks
an otherwise eligible filing; it only prevents establishing required-credit eligibility.
"""
import json
import sys
from datetime import datetime, timedelta

ACTIVE_STATUSES = {"OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"}
TIER_LIMITS = {"entry": 2, "entry tier": 2, "mid": 3, "mid tier": 3,
               "premium": 4, "premium tier": 4, "elite": 5, "elite tier": 5}
VALID_PINS = {"yes_shared", "yes_observed", "no", "unknown"}


def get(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else default


def date_value(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def weekdays_after(start, end):
    if not start or not end or end < start:
        return None
    days = 0
    cursor = start
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            days += 1
    return days


def liability(statement, discovery):
    if not statement or not discovery:
        return {"tier": "unknown", "message": "Statement date is needed only for a personalized liability assessment; it does not prevent filing."}
    if discovery < statement:
        return {"tier": "needs_review", "message": "Discovery predates the supplied statement; verify the applicable statement date."}
    business = weekdays_after(statement, discovery)
    calendar = (discovery - statement).days
    if business <= 2:
        return {"tier": "within_2_business_days", "maximum_liability": 50,
                "business_days_from_statement": business, "calendar_days_from_statement": calendar}
    if calendar <= 60:
        return {"tier": "within_60_days", "maximum_liability": 500,
                "business_days_from_statement": business, "calendar_days_from_statement": calendar}
    return {"tier": "after_60_days", "maximum_liability": None,
            "business_days_from_statement": business, "calendar_days_from_statement": calendar,
            "message": "Liability may be unlimited and recovery may be unavailable."}


def assess(data):
    account = get(data, "account", {})
    card = get(data, "card", {})
    transaction = get(data, "transaction", {})
    claim = get(data, "claim", {})
    reasons, warnings = [], []

    today = date_value(get(data, "current_date"))
    transaction_date = date_value(get(transaction, "date"))
    discovery = date_value(get(claim, "discovery_date"))
    statement = date_value(get(claim, "statement_date"))
    opened = date_value(get(account, "date_opened"))
    account_id = get(account, "account_id")
    user_id = get(claim, "user_id")

    if get(data, "verified_and_logged") is not True:
        reasons.append("Customer identity must be successfully verified and logged.")
    if get(account, "account_type", "").lower() != "checking":
        reasons.append("The selected linked account must be a checking account.")
    if get(account, "status", "").upper() != "OPEN":
        reasons.append("The linked checking account must be OPEN.")
    if get(account, "has_holds_or_restrictions") is True:
        reasons.append("The checking account has a hold or restriction.")
    if not account_id:
        reasons.append("A checking account ID is required.")
    if not get(card, "card_id"):
        reasons.append("A linked debit-card ID is required.")
    if get(card, "account_id") != account_id:
        reasons.append("The debit card is not linked to the selected checking account.")
    if not user_id or get(card, "user_id") != user_id:
        reasons.append("The cardholder user ID must match the verified filing user.")
    if get(transaction, "account_id") != account_id:
        reasons.append("The selected transaction does not belong to the checking account.")
    if get(transaction, "type") != "atm_withdrawal":
        reasons.append("The selected transaction must be an ATM withdrawal.")
    if not get(transaction, "transaction_id"):
        reasons.append("An exact transaction ID is required.")
    if not today or not transaction_date:
        reasons.append("Valid current and transaction dates are required.")
    elif transaction_date > today or (today - transaction_date).days > 60:
        reasons.append("The transaction must be no more than 60 calendar days old.")

    amount = None
    try:
        amount = float(get(claim, "disputed_amount"))
        debit = abs(float(get(transaction, "amount")))
        if amount < 1.0:
            reasons.append("The disputed amount must be at least $1.00.")
        if amount > debit:
            reasons.append("The cash shortage cannot exceed the withdrawal amount.")
    except (TypeError, ValueError):
        reasons.append("A numeric disputed amount is required.")

    tier = str(get(account, "account_class", "")).strip().lower()
    limit = TIER_LIMITS.get(tier)
    active_count = None
    if limit is None:
        reasons.append("Checking-account tier/class is missing or unsupported.")
    else:
        disputes = get(data, "disputes", [])
        if not isinstance(disputes, list):
            reasons.append("Dispute history must be a list of runtime dispute records.")
        else:
            active_count = sum(
                1 for dispute in disputes
                if isinstance(dispute, dict)
                and get(dispute, "account_id") == account_id
                and str(get(dispute, "status", "")).upper() in ACTIVE_STATUSES
            )
            if active_count + 1 > limit:
                reasons.append("Filing would exceed this account tier's active-dispute limit.")

    if not discovery:
        reasons.append("A valid discovery date is required.")
    if get(claim, "card_in_possession") not in (True, False):
        reasons.append("Physical-card possession must be recorded as a boolean.")
    pin = get(claim, "pin_compromised")
    if pin not in VALID_PINS:
        reasons.append("PIN-compromise response must use an allowed enum value.")
    if get(claim, "contacted_merchant") not in (True, False):
        reasons.append("ATM-operator contact must be recorded as a boolean.")
    if get(claim, "written_statement_provided") not in (True, False):
        reasons.append("Written-statement consent must be recorded as a boolean.")

    owner = get(claim, "atm_owner")
    if owner not in ("rho_bank", "third_party"):
        reasons.append("Identify whether the ATM is Rho-Bank or third-party before filing.")
    journal_confirmed = get(claim, "journal_discrepancy_confirmed")
    if owner == "rho_bank" and journal_confirmed is None:
        warnings.append("Review corresponding Rho-Bank ATM transaction/journal information; this does not block a formal filing.")

    if statement and discovery:
        timely = discovery >= statement and (discovery - statement).days <= 60
    elif get(claim, "reported_within_60_days_of_statement") in (True, False):
        timely = get(claim, "reported_within_60_days_of_statement")
    else:
        timely = None
        warnings.append("Required provisional-credit timing is not established without a statement date or authoritative timing flag. File the eligible dispute; follow up on timing separately.")

    standing_open = get(account, "status", "").upper() == "OPEN" and get(account, "has_holds_or_restrictions") is False
    provisional = bool(timely is True and get(claim, "written_statement_provided") is True and standing_open and pin != "yes_shared")
    is_new = bool(opened and today and 0 <= (today - opened).days < 30)
    immediate = bool(provisional and owner == "rho_bank" and journal_confirmed is True)
    if pin == "yes_shared":
        warnings.append("Voluntary PIN sharing means provisional credit is not required.")
    if owner == "third_party" and amount is not None and amount > 200:
        warnings.append("Third-party ATM discrepancy above $200 requires an EFT Error Resolution Affidavit.")

    payload = {
        "transaction_id": get(transaction, "transaction_id"),
        "account_id": account_id,
        "card_id": get(card, "card_id"),
        "user_id": user_id,
        "dispute_category": "atm_cash_discrepancy",
        "transaction_date": get(transaction, "date"),
        "discovery_date": get(claim, "discovery_date"),
        "disputed_amount": amount,
        "transaction_type": "atm_withdrawal",
        "card_in_possession": get(claim, "card_in_possession"),
        "pin_compromised": pin,
        "contacted_merchant": get(claim, "contacted_merchant"),
        "police_report_filed": False,
        "written_statement_provided": get(claim, "written_statement_provided"),
        "provisional_credit_eligible": provisional,
        "card_action": "keep_active"
    }
    return {
        "ready_to_file": not reasons,
        "blocking_reasons": reasons,
        "warnings": warnings,
        "active_dispute_count_for_account": active_count,
        "account_dispute_limit": limit,
        "liability_assessment": liability(statement, discovery),
        "provisional_credit": {
            "eligible": provisional,
            "timely_reporting_established": timely,
            "immediate_credit_indicated": immediate,
            "standard_timeline_business_days": 20 if is_new else 10,
            "investigation_timeline_business_days": 45
        },
        "filing_payload": payload
    }


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(assess(source), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready_to_file": False, "blocking_reasons": [str(exc)]}, separators=(",", ":")))
