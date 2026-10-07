#!/usr/bin/env python3
"""Assess a debit-card ATM cash-discrepancy filing from supplied runtime facts.

Input is one JSON object described in SKILL.md. Output contains readiness, reasons,
policy assessments, and a candidate file_debit_card_transaction_dispute_6281 payload.
No network, banking, or filesystem operations are performed.
"""
import json
import sys
from datetime import datetime, date, timedelta

ACTIVE_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
TIER_LIMITS = {
    "entry": 2, "entry tier": 2,
    "mid": 3, "mid tier": 3,
    "premium": 4, "premium tier": 4,
    "elite": 5, "elite tier": 5,
}
QUALIFYING_CATEGORIES = {
    "unauthorized_transaction", "card_present_fraud", "card_not_present_fraud",
    "atm_cash_discrepancy", "duplicate_charge",
}
VALID_PINS = {"yes_shared", "yes_observed", "no", "unknown"}


def value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else default


def parse_date(raw):
    if not raw or not isinstance(raw, str):
        return None
    raw = raw.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def business_days_between(start, end):
    """Weekday count after start through end; holidays are intentionally unknown."""
    if not start or not end or end < start:
        return None
    total = 0
    cursor = start
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            total += 1
    return total


def liability(statement_date, discovery_date):
    if not statement_date or not discovery_date:
        return {"tier": "unknown", "message": "Statement date is needed for a personalized Regulation E liability tier."}
    if discovery_date < statement_date:
        return {"tier": "needs_review", "message": "Discovery predates the supplied statement; verify the applicable statement date."}
    business_days = business_days_between(statement_date, discovery_date)
    calendar_days = (discovery_date - statement_date).days
    if business_days <= 2:
        tier, maximum = "within_2_business_days", 50
    elif calendar_days <= 60:
        tier, maximum = "within_60_days", 500
    else:
        tier, maximum = "after_60_days", None
    return {"tier": tier, "business_days_from_statement": business_days,
            "calendar_days_from_statement": calendar_days, "maximum_liability": maximum,
            "message": ("Maximum liability is $%s." % maximum) if maximum is not None else "Liability may be unlimited and funds may not be recoverable."}


def main(data):
    account = value(data, "account", {})
    card = value(data, "card", {})
    tx = value(data, "transaction", {})
    claim = value(data, "claim", {})
    today = parse_date(value(data, "current_date"))
    tx_date = parse_date(value(tx, "date"))
    discovery = parse_date(value(claim, "discovery_date"))
    statement = parse_date(value(claim, "statement_date"))
    opened = parse_date(value(account, "date_opened"))
    reasons, warnings = [], []

    if value(data, "verified_and_logged") is not True:
        reasons.append("Customer identity must be verified and the verification must be logged.")
    if value(account, "account_type", "").lower() != "checking":
        reasons.append("The linked account must be a checking account.")
    if value(account, "status", "").upper() != "OPEN":
        reasons.append("The linked checking account must be OPEN.")
    if value(account, "has_holds_or_restrictions") is True:
        reasons.append("The checking account has a hold or restriction.")
    if not value(account, "account_id"):
        reasons.append("A checking account ID is required.")
    if not value(card, "card_id"):
        reasons.append("A linked debit-card ID is required.")
    if value(card, "account_id") != value(account, "account_id"):
        reasons.append("The debit card is not linked to the selected checking account.")
    if not value(claim, "user_id") or value(card, "user_id") != value(claim, "user_id"):
        reasons.append("Cardholder user ID must match the verified filing user.")
    if value(tx, "account_id") != value(account, "account_id"):
        reasons.append("The transaction does not belong to the selected checking account.")
    if value(tx, "type") != "atm_withdrawal":
        reasons.append("The selected transaction is not an ATM withdrawal.")
    if not value(tx, "transaction_id"):
        reasons.append("An exact transaction ID is required.")
    if not tx_date or not today:
        reasons.append("Valid transaction and current dates are required.")
    elif tx_date > today or (today - tx_date).days > 60:
        reasons.append("The transaction must be no more than 60 calendar days old.")

    amount = value(claim, "disputed_amount")
    try:
        amount = float(amount)
        if amount < 1:
            reasons.append("The disputed amount must be at least $1.00.")
        tx_amount = abs(float(value(tx, "amount")))
        if amount > tx_amount:
            reasons.append("The shortage cannot exceed the ATM transaction amount.")
    except (TypeError, ValueError):
        reasons.append("A numeric disputed amount is required.")
        amount = None

    tier_key = str(value(account, "account_class", "")).strip().lower()
    limit = TIER_LIMITS.get(tier_key)
    if limit is None:
        reasons.append("Checking-account tier/class is missing or unsupported.")
        active_count = None
    else:
        disputes = value(data, "disputes", [])
        if not isinstance(disputes, list):
            reasons.append("Dispute history must be a list of runtime dispute records.")
            active_count = None
        else:
            active_count = sum(1 for d in disputes if isinstance(d, dict)
                               and value(d, "account_id") == value(account, "account_id")
                               and str(value(d, "status", "")).upper() in ACTIVE_STATUSES)
            if active_count + 1 > limit:
                reasons.append("Filing would exceed this account tier's maximum active disputes.")

    pin = value(claim, "pin_compromised")
    if pin not in VALID_PINS:
        reasons.append("PIN-compromise response must use an allowed enum value.")
    if not discovery:
        reasons.append("A valid discovery date is required.")
    if value(claim, "card_in_possession") not in (True, False):
        reasons.append("Physical-card possession must be recorded as a boolean.")
    if value(claim, "contacted_merchant") not in (True, False):
        reasons.append("ATM-operator contact must be recorded as a boolean.")
    if value(claim, "written_statement_provided") not in (True, False):
        reasons.append("Written-statement consent must be recorded as a boolean.")

    statement_timely = None
    if statement and discovery:
        statement_timely = discovery >= statement and (discovery - statement).days <= 60
    elif value(claim, "reported_within_60_days_of_statement") in (True, False):
        statement_timely = value(claim, "reported_within_60_days_of_statement")
    else:
        warnings.append("Statement date or an authoritative timely-reporting flag is needed to establish required provisional credit.")

    open_standing = (value(account, "status", "").upper() == "OPEN" and
                     value(account, "has_holds_or_restrictions") is False)
    basic_eligible = (statement_timely is True and value(claim, "written_statement_provided") is True
                      and open_standing and pin != "yes_shared")
    account_new = bool(opened and today and 0 <= (today - opened).days < 30)
    cnp_exception = account_new and value(claim, "transaction_type", "atm_withdrawal") == "online_purchase"
    provisional_eligible = bool(basic_eligible and not cnp_exception)
    journal_confirmed = value(claim, "journal_discrepancy_confirmed")
    atm_owner = value(claim, "atm_owner")
    immediate = provisional_eligible and atm_owner == "rho_bank" and journal_confirmed is True
    if atm_owner not in ("rho_bank", "third_party"):
        warnings.append("Confirm whether the ATM is Rho-Bank branded or third-party.")
    if atm_owner == "rho_bank" and journal_confirmed is None:
        warnings.append("Review Rho-Bank ATM journal/transaction information before deciding whether immediate credit applies.")
    if atm_owner == "third_party" and amount is not None and amount > 200:
        warnings.append("Third-party ATM discrepancy over $200 requires an EFT Error Resolution Affidavit.")
    if pin == "yes_shared":
        warnings.append("Voluntarily sharing a PIN means provisional credit is not required.")
    if value(claim, "contacted_merchant") is False:
        warnings.append("For a non-fraud claim without prior operator contact, provisional credit can be discretionary; a confirmed Rho-Bank discrepancy follows the immediate-credit process.")

    payload = {
        "transaction_id": value(tx, "transaction_id"),
        "account_id": value(account, "account_id"),
        "card_id": value(card, "card_id"),
        "user_id": value(claim, "user_id"),
        "dispute_category": "atm_cash_discrepancy",
        "transaction_date": value(tx, "date"),
        "discovery_date": value(claim, "discovery_date"),
        "disputed_amount": amount,
        "transaction_type": "atm_withdrawal",
        "card_in_possession": value(claim, "card_in_possession"),
        "pin_compromised": pin,
        "contacted_merchant": value(claim, "contacted_merchant"),
        "police_report_filed": False,
        "written_statement_provided": value(claim, "written_statement_provided"),
        "provisional_credit_eligible": provisional_eligible,
        "card_action": "keep_active",
    }
    return {
        "ready_to_file": not reasons,
        "blocking_reasons": reasons,
        "warnings": warnings,
        "active_dispute_count_for_account": active_count,
        "account_dispute_limit": limit,
        "liability_assessment": liability(statement, discovery),
        "provisional_credit": {
            "eligible": provisional_eligible,
            "timely_reporting_established": statement_timely,
            "immediate_credit_indicated": immediate,
            "standard_timeline_business_days": 20 if account_new else 10,
            "investigation_timeline_business_days": 45,
        },
        "filing_payload": payload,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(raw), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ready_to_file": False, "blocking_reasons": [str(exc)]}, separators=(",", ":")))
