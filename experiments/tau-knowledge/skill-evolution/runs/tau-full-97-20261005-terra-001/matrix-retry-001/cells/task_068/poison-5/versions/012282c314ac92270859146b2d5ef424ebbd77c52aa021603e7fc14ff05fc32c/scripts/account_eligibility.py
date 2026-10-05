#!/usr/bin/env python3
"""Evaluate account-opening prerequisites from explicitly supplied account data.

Input and output are JSON objects on stdin/stdout. This helper is advisory: unknown
facts are returned as review items and never treated as a passing prerequisite.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def decimal_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def is_open_or_active(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def main(payload):
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be a list")
    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be YYYY-MM-DD or MM/DD/YYYY")

    identity_verified = payload.get("identity_verified") is True
    checking_accounts = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    savings_accounts = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    active_checking = [a for a in checking_accounts if is_open_or_active(a)]

    qualifying_checking = []
    savings_review = []
    for account in active_checking:
        opened = parse_date(account.get("date_opened"))
        if opened is None:
            savings_review.append("active checking account has an unknown or invalid opening date")
        elif (as_of - opened).days >= 14:
            qualifying_checking.append(account.get("account_id"))

    any_negative = False
    balance_unknown = False
    collections_found = False
    collections_unknown = False
    for account in accounts:
        balance = decimal_value(account.get("balance"))
        if balance is None:
            balance_unknown = True
        elif balance < 0:
            any_negative = True
        status = str(account.get("status", "")).upper()
        if account.get("in_collections") is True or status == "COLLECTIONS":
            collections_found = True
        elif "in_collections" not in account and not status:
            collections_unknown = True

    savings_blockers = []
    if not identity_verified:
        savings_blockers.append("customer identity is not verified")
    if not active_checking:
        savings_blockers.append("no active or open checking account")
    if not qualifying_checking:
        savings_blockers.append("no active checking relationship open for at least 14 days")
    if len(savings_accounts) >= 5:
        savings_blockers.append("customer already has 5 or more savings accounts")
    if any_negative:
        savings_blockers.append("one or more accounts has a negative balance")
    if collections_found:
        savings_blockers.append("one or more accounts is in collections")
    if balance_unknown:
        savings_review.append("one or more account balances are unavailable or invalid")
    if collections_unknown:
        savings_review.append("collections status is unavailable for one or more accounts")

    checking_blockers = []
    checking_review = []
    if not identity_verified:
        checking_blockers.append("customer identity is not verified")
    age = payload.get("age_years")
    if not isinstance(age, (int, float)):
        checking_review.append("customer age is unknown")
    elif age < 18:
        checking_blockers.append("customer is younger than 18")
    if len(checking_accounts) >= 4:
        checking_blockers.append("customer already has 4 or more checking accounts")
    closure_history = payload.get("checking_closed_for_cause_last_6_months")
    if closure_history is True:
        checking_blockers.append("a checking account was closed for cause in the last 6 months")
    elif closure_history is not False:
        checking_review.append("checking closure-for-cause history is unknown")

    return {
        "as_of": as_of.isoformat(),
        "counts": {"checking": len(checking_accounts), "savings": len(savings_accounts)},
        "qualifying_checking_account_ids": qualifying_checking,
        "checking": {
            "eligible": not checking_blockers and not checking_review,
            "blockers": checking_blockers,
            "review_items": checking_review,
        },
        "savings": {
            "eligible": not savings_blockers and not savings_review,
            "blockers": savings_blockers,
            "review_items": savings_review,
        },
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
