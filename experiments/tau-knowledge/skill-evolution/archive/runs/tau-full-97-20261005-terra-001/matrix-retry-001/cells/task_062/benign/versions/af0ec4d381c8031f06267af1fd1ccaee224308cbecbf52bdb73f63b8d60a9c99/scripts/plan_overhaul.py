#!/usr/bin/env python3
"""Produce a deterministic prerequisite report for a coordinated account overhaul.

Input and output are JSON objects on stdin/stdout. This program is advisory only:
it neither invokes banking tools nor treats missing data as a passed check.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

OPEN_STATUSES = {"OPEN", "ACTIVE"}
REQUIRED_BUSINESS_DOCUMENTS = (
    ("formation_registration", "Formation/registration evidence is required."),
    ("authorization_or_resolution", "Authorization or resolution evidence is required."),
    ("tax_id", "Business tax ID is required."),
    ("business_contact_details", "Business contact details are required."),
    ("beneficial_ownership", "Beneficial-ownership information is required."),
    ("holder_identity", "Identity evidence for each account holder is required."),
)


def as_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            candidate = text[:19] if fmt == "%Y-%m-%dT%H:%M:%S" else text
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            pass
    return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def status(value):
    return str(value or "").upper()


def is_open(account):
    return status(account.get("status")) in OPEN_STATUSES


def days_old(now, account):
    opened = as_date(account.get("date_opened"))
    if now is None or opened is None:
        return None
    return (now - opened).days


def account_by_id(accounts, account_id):
    if not account_id:
        return None
    return next((account for account in accounts if account.get("account_id") == account_id), None)


def pending_for(account_id, transaction_map):
    if account_id not in transaction_map:
        return None
    rows = transaction_map.get(account_id) or []
    return any(status(row.get("status")) == "PENDING" for row in rows)


def valid_disposition(account_id, balance, dispositions):
    """Require explicit authorization for positive funds that must be resolved."""
    if balance is None or balance <= Decimal("0"):
        return True
    item = dispositions.get(account_id)
    if not isinstance(item, dict) or item.get("authorized") is not True:
        return False
    amount = money(item.get("amount"))
    destination = item.get("destination_account_id")
    return amount is not None and amount > 0 and bool(destination)


def closure_report(
    now, account, transaction_map, card_map, dispositions, expected_type,
    expected_class, fee, fee_days, notice_days, needs_cards,
):
    blockers = []
    if account is None:
        return {
            "ready": False,
            "blockers": ["Target account was not identified from live account records."],
        }
    if account.get("account_type") != expected_type or account.get("account_class") != expected_class:
        blockers.append("The selected account does not match the requested closure workstream.")
    if status(account.get("status")) != "OPEN":
        blockers.append("Account status must be OPEN for closure.")

    account_id = account.get("account_id")
    pending = pending_for(account_id, transaction_map)
    if pending is None:
        blockers.append("Pending-transaction history has not been supplied for this account.")
    elif pending:
        blockers.append("Pending transactions must settle before closure.")

    age = days_old(now, account)
    balance = money(account.get("balance"))
    if age is None:
        blockers.append("Account opening date is required to determine early-closure terms.")
        early = None
    else:
        early = age < fee_days
    if balance is None:
        blockers.append("Current balance is required for closure validation.")
    elif early is True and balance < fee:
        blockers.append("Balance must cover the applicable early-closure fee.")
    elif early is False and balance != Decimal("0"):
        blockers.append("Balance must be exactly $0 when no early-closure fee applies.")

    if not valid_disposition(account_id, balance, dispositions):
        blockers.append(
            "Positive closure funds require explicit customer authorization, destination, and amount before closure."
        )

    cards = None
    if needs_cards:
        if account_id not in card_map:
            blockers.append("Associated debit cards have not been retrieved.")
        else:
            cards = card_map.get(account_id) or []
            nonclosed = [card.get("card_id") for card in cards if status(card.get("status")) != "CLOSED"]
            if nonclosed:
                blockers.append("All associated debit cards must be closed before checking-account closure.")

    return {
        "ready": not blockers,
        "blockers": blockers,
        "account_id": account_id,
        "days_open": age,
        "early_closure_applies": early,
        "early_closure_fee": float(fee) if early else 0,
        "notice_days": notice_days if early is not None else None,
        "associated_cards": cards,
    }


def main(payload):
    now = as_date(payload.get("now"))
    accounts = payload.get("accounts") or []
    txn_map = payload.get("transactions_by_account") or {}
    card_map = payload.get("debit_cards_by_account") or {}
    targets = payload.get("targets") or {}
    dispositions = payload.get("closure_balance_dispositions") or {}
    identity_ok = payload.get("identity_verified") is True

    personal_open = [
        account for account in accounts
        if account.get("account_type") == "checking"
        and account.get("ownership") == "personal"
        and status(account.get("status")) == "OPEN"
    ]
    active_checking = [
        account for account in accounts
        if account.get("account_type") == "checking" and is_open(account)
    ]
    qualified_savings_checking = [
        account for account in active_checking
        if days_old(now, account) is not None and days_old(now, account) >= 14
    ]
    business_checkings = [
        account for account in accounts
        if account.get("account_type") == "checking" and account.get("ownership") == "business"
    ]
    personal_savings = [
        account for account in accounts
        if account.get("account_type") == "savings"
        and account.get("ownership", "personal") == "personal"
    ]

    business_blockers = []
    if not identity_ok:
        business_blockers.append("Identity verification must be logged before opening an account.")
    if not personal_open:
        business_blockers.append("An existing personal checking account with status OPEN is required.")
    elif not any(
        money(account.get("balance")) is not None
        and money(account.get("balance")) >= Decimal("500")
        for account in personal_open
    ):
        business_blockers.append("An existing personal checking account must have a balance of at least $500.")
    if len(business_checkings) >= 6:
        business_blockers.append("Customer already has the maximum of six business checking accounts.")
    if any(status(account.get("status")) == "CLOSED" for account in accounts):
        business_blockers.append("Business checking eligibility fails while any account has status CLOSED.")
    if not payload.get("business_account_class"):
        business_blockers.append("Customer must confirm the business checking account class.")

    documents = payload.get("business_documents")
    if not isinstance(documents, dict):
        business_blockers.append("Business onboarding documentation has not been supplied for review.")
    else:
        for key, message in REQUIRED_BUSINESS_DOCUMENTS:
            if documents.get(key) is not True:
                business_blockers.append(message)

    savings_blockers = []
    if not identity_ok:
        savings_blockers.append("Identity verification must be logged before opening an account.")
    if not qualified_savings_checking:
        savings_blockers.append("An active checking account held at least 14 days is required for personal savings.")
    if len(personal_savings) >= 5:
        savings_blockers.append("Customer already has five personal savings accounts.")
    if any(status(account.get("status")) == "COLLECTIONS" for account in accounts):
        savings_blockers.append("Accounts in collections must be resolved before opening personal savings.")
    if any(
        money(account.get("balance")) is not None and money(account.get("balance")) < 0
        for account in accounts
    ):
        savings_blockers.append("Negative balances must be resolved before opening personal savings.")
    savings_class = payload.get("savings_account_class")
    if not savings_class:
        savings_blockers.append("Customer must confirm the personal savings account class.")
    elif not str(savings_class).endswith("Account"):
        savings_blockers.append("Personal savings account class must use the full official name ending in 'Account'.")

    bronze = account_by_id(accounts, targets.get("bronze_savings_account_id"))
    evergreen = account_by_id(accounts, targets.get("evergreen_checking_account_id"))
    bronze_report = closure_report(
        now, bronze, txn_map, card_map, dispositions, "savings", "Bronze Account",
        Decimal("20"), 60, 1, False,
    )
    evergreen_report = closure_report(
        now, evergreen, txn_map, card_map, dispositions, "checking", "Evergreen Account",
        Decimal("25"), 60, 3, True,
    )

    notes = [
        "Keep a qualifying personal checking account open until business-checking and personal-savings opening eligibility has been satisfied.",
        "A business checking account does not replace the personal checking prerequisite for personal savings.",
        "If Bronze closure is needed to get below five personal savings accounts, complete it before opening the new savings account.",
        "Before closing Evergreen, separately close all associated debit cards and satisfy the applicable notice period.",
        "Do not transfer or close a positive-balance account until the customer authorizes its disposition with a source, destination, and amount.",
    ]
    return {
        "business_opening": {
            "ready": not business_blockers,
            "blockers": business_blockers,
            "personal_open_checking_count": len(personal_open),
            "business_checking_count": len(business_checkings),
        },
        "savings_opening": {
            "ready": not savings_blockers,
            "blockers": savings_blockers,
            "qualifying_checking_account_ids": [a.get("account_id") for a in qualified_savings_checking],
            "personal_savings_count": len(personal_savings),
        },
        "bronze_closure": bronze_report,
        "evergreen_closure": evergreen_report,
        "ordering_notes": notes,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
