#!/usr/bin/env python3
"""Assess a runtime-supplied debit-card ATM cash-discrepancy claim.

Input: one JSON object on stdin using the schema documented in SKILL.md.
Output: one JSON object on stdout containing readiness, explanations, and a complete
candidate filing payload. This script has no network, banking, or filesystem side effects.
"""
import json
import sys
from datetime import datetime, timedelta

ACTIVE_STATUSES = {
    "OPEN", "PENDING_DOCUMENTATION", "UNDER_REVIEW", "PROVISIONAL_CREDIT_ISSUED"
}
TIER_LIMITS = {
    "entry": 2, "entry tier": 2,
    "mid": 3, "mid tier": 3,
    "premium": 4, "premium tier": 4,
    "elite": 5, "elite tier": 5,
}
VALID_PINS = {"yes_shared", "yes_observed", "no", "unknown"}


def value(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else default


def parse_date(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            pass
    return None


def business_days_after(start, end):
    if not start or not end or end < start:
        return None
    count = 0
    cursor = start
    while cursor < end:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            count += 1
    return count


def liability_assessment(statement, discovery):
    if not statement or not discovery:
        return {
            "tier": "unknown",
            "message": (
                "A statement date is needed only for a personalized liability assessment; "
                "it is not required to file the dispute."
            ),
        }
    if discovery < statement:
        return {
            "tier": "reported_before_statement",
            "message": "The report predates the supplied statement and is not late relative to it.",
        }
    business = business_days_after(statement, discovery)
    calendar = (discovery - statement).days
    if business <= 2:
        return {
            "tier": "within_2_business_days", "maximum_liability": 50,
            "business_days_from_statement": business, "calendar_days_from_statement": calendar,
        }
    if calendar <= 60:
        return {
            "tier": "within_60_days", "maximum_liability": 500,
            "business_days_from_statement": business, "calendar_days_from_statement": calendar,
        }
    return {
        "tier": "after_60_days", "maximum_liability": None,
        "business_days_from_statement": business, "calendar_days_from_statement": calendar,
        "message": "Liability may be unlimited and recovery may be unavailable.",
    }


def active_disputes(disputes, account_id):
    if not isinstance(disputes, list):
        return None
    return sum(
        1 for dispute in disputes
        if isinstance(dispute, dict)
        and value(dispute, "account_id") == account_id
        and str(value(dispute, "status", "")).upper() in ACTIVE_STATUSES
    )


def timely_reporting(claim, transaction_date, discovery, statement):
    """Return (timely-or-None, reason) without manufacturing a statement date.

    A report on the transaction date necessarily precedes or coincides with any statement
    that later displays that transaction, so it is timely under the 60-day statement rule.
    """
    supplied = value(claim, "reported_within_60_days_of_statement")
    if supplied in (True, False):
        return supplied, "authoritative_reporting_flag"
    if statement and discovery:
        return (
            discovery <= statement or (discovery - statement).days <= 60,
            "statement_date",
        )
    if transaction_date and discovery and discovery == transaction_date:
        return True, "reported_on_transaction_date"
    return None, "statement_timing_not_established"


def assess(data):
    account = value(data, "account", {})
    card = value(data, "card", {})
    transaction = value(data, "transaction", {})
    claim = value(data, "claim", {})
    reasons = []
    warnings = []

    today = parse_date(value(data, "current_date"))
    transaction_date = parse_date(value(transaction, "date"))
    discovery = parse_date(value(claim, "discovery_date"))
    statement = parse_date(value(claim, "statement_date"))
    opened = parse_date(value(account, "date_opened"))
    account_id = value(account, "account_id")
    user_id = value(claim, "user_id")

    if value(data, "verified_and_logged") is not True:
        reasons.append("Customer identity must be successfully verified and logged.")
    if str(value(account, "account_type", "")).lower() != "checking":
        reasons.append("The selected linked account must be a checking account.")
    if str(value(account, "status", "")).upper() != "OPEN":
        reasons.append("The linked checking account must be OPEN.")
    if value(account, "has_holds_or_restrictions") is True:
        reasons.append("The checking account has a hold or restriction.")
    if not account_id:
        reasons.append("A checking account ID is required.")
    if not value(card, "card_id"):
        reasons.append("A linked debit-card ID is required.")
    if value(card, "account_id") != account_id:
        reasons.append("The debit card is not linked to the selected checking account.")
    if not user_id or value(card, "user_id") != user_id:
        reasons.append("The cardholder user ID must match the verified filing user.")
    if value(transaction, "account_id") != account_id:
        reasons.append("The selected transaction does not belong to the checking account.")
    if value(transaction, "type") != "atm_withdrawal":
        reasons.append("The selected transaction must be an ATM withdrawal.")
    if not value(transaction, "transaction_id"):
        reasons.append("An exact transaction ID is required.")
    if not today or not transaction_date:
        reasons.append("Valid current and transaction dates are required.")
    elif transaction_date > today or (today - transaction_date).days > 60:
        reasons.append("The transaction must be no more than 60 calendar days old.")

    amount = None
    try:
        amount = float(value(claim, "disputed_amount"))
        withdrawal = abs(float(value(transaction, "amount")))
        if amount < 1.0:
            reasons.append("The disputed amount must be at least $1.00.")
        if amount > withdrawal:
            reasons.append("The cash shortage cannot exceed the withdrawal amount.")
    except (TypeError, ValueError):
        reasons.append("A numeric disputed amount is required.")

    if not discovery:
        reasons.append("A valid discovery date is required.")
    elif transaction_date and discovery < transaction_date:
        reasons.append("The discovery date cannot precede the ATM transaction date.")
    if value(claim, "card_in_possession") not in (True, False):
        reasons.append("Physical-card possession must be recorded as a boolean.")
    pin = value(claim, "pin_compromised")
    if pin not in VALID_PINS:
        reasons.append("PIN-compromise response must use an allowed enum value.")
    if value(claim, "contacted_merchant") not in (True, False):
        reasons.append("ATM-operator contact must be recorded as a boolean.")
    if value(claim, "written_statement_provided") not in (True, False):
        reasons.append("Written-statement consent must be recorded as a boolean.")

    owner = value(claim, "atm_owner")
    if owner not in ("rho_bank", "third_party"):
        reasons.append("Identify whether the ATM is Rho-Bank or third-party before filing.")
    journal_confirmed = value(claim, "journal_discrepancy_confirmed")
    if owner == "rho_bank" and journal_confirmed is None:
        warnings.append(
            "Review available Rho-Bank ATM transaction/journal information; lack of "
            "corroboration does not prevent a formal filing."
        )

    disputes = value(data, "disputes", [])
    active_count = active_disputes(disputes, account_id)
    tier = str(value(account, "account_class", "")).strip().lower()
    limit = TIER_LIMITS.get(tier)
    if active_count is None:
        reasons.append("Dispute history must be a list of runtime dispute records.")
    elif limit is not None:
        if active_count + 1 > limit:
            reasons.append("Filing would exceed this account tier's active-dispute limit.")
    elif active_count >= 2:
        reasons.append(
            "The account has two or more active disputes and its tier/capacity must be "
            "confirmed before another dispute is filed."
        )
    else:
        warnings.append(
            "The product label is not a documented tier, but the account has capacity under "
            "every documented tier maximum because it has fewer than two active disputes."
        )

    timely, timing_basis = timely_reporting(claim, transaction_date, discovery, statement)
    if timely is None:
        warnings.append(
            "Statement-relative reporting timing is not established. This is not a filing "
            "block; obtain it for provisional-credit follow-up."
        )
    elif timely is False:
        warnings.append("The supplied reporting timing does not establish required provisional credit.")

    # The account lookup may omit a restriction field. An affirmative hold blocks
    # eligibility; absence of an affirmative hold is treated as no known restriction.
    standing_open = (
        str(value(account, "status", "")).upper() == "OPEN"
        and value(account, "has_holds_or_restrictions") is not True
    )
    provisional = bool(
        timely is True
        and value(claim, "written_statement_provided") is True
        and standing_open
        and pin != "yes_shared"
    )
    is_new = bool(opened and today and 0 <= (today - opened).days < 30)
    immediate = bool(provisional and owner == "rho_bank" and journal_confirmed is True)
    if pin == "yes_shared":
        warnings.append("Voluntary PIN sharing means provisional credit is not required.")
    if owner == "third_party" and amount is not None and amount > 200:
        warnings.append("A third-party ATM discrepancy above $200 requires an EFT Error Resolution Affidavit.")

    payload = {
        "transaction_id": value(transaction, "transaction_id"),
        "account_id": account_id,
        "card_id": value(card, "card_id"),
        "user_id": user_id,
        "dispute_category": "atm_cash_discrepancy",
        "transaction_date": value(transaction, "date"),
        "discovery_date": value(claim, "discovery_date"),
        "disputed_amount": amount,
        "transaction_type": "atm_withdrawal",
        "card_in_possession": value(claim, "card_in_possession"),
        "pin_compromised": pin,
        "contacted_merchant": value(claim, "contacted_merchant"),
        "police_report_filed": False,
        "written_statement_provided": value(claim, "written_statement_provided"),
        "provisional_credit_eligible": provisional,
        "card_action": "keep_active",
    }
    return {
        "ready_to_file": not reasons,
        "blocking_reasons": reasons,
        "warnings": warnings,
        "active_dispute_count_for_account": active_count,
        "account_dispute_limit": limit,
        "liability_assessment": liability_assessment(statement, discovery),
        "provisional_credit": {
            "eligible": provisional,
            "timely_reporting_established": timely,
            "timing_basis": timing_basis,
            "immediate_credit_indicated": immediate,
            "standard_timeline_business_days": 20 if is_new else 10,
            "investigation_timeline_business_days": 45,
        },
        "filing_payload": payload,
    }


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(assess(source), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({
            "ready_to_file": False,
            "blocking_reasons": [str(exc)],
        }, separators=(",", ":"), sort_keys=True))
