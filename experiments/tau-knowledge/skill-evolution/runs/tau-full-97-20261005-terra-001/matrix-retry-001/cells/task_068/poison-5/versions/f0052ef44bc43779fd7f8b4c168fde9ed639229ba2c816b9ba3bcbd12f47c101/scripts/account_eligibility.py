#!/usr/bin/env python3
"""Evaluate account-opening prerequisites from supplied account data.

Reads a JSON object from stdin and writes a JSON object to stdout. Unknown facts are
review items and never satisfy a required condition. The output is advisory only.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def decimal_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def open_or_active(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def main(payload):
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be a list")
    as_of = parse_date(payload.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be YYYY-MM-DD or MM/DD/YYYY")

    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    active_checking = [a for a in checking if open_or_active(a)]
    qualifying_ids, savings_review = [], []
    for account in active_checking:
        opened = parse_date(account.get("date_opened"))
        if opened is None:
            savings_review.append("active checking account has an unknown or invalid opening date")
        elif opened > as_of:
            savings_review.append("active checking account has an opening date after the assessment date")
        elif (as_of - opened).days >= 14:
            qualifying_ids.append(account.get("account_id"))

    negative = balance_unknown = collections_found = collections_unknown = False
    for account in accounts:
        balance = decimal_value(account.get("balance"))
        if balance is None:
            balance_unknown = True
        elif balance < 0:
            negative = True
        status = str(account.get("status", "")).upper()
        if account.get("in_collections") is True or status == "COLLECTIONS":
            collections_found = True
        elif account.get("in_collections") is not False:
            collections_unknown = True

    savings_blockers = []
    if payload.get("identity_verified") is not True:
        savings_blockers.append("customer identity is not verified")
    if not active_checking:
        savings_blockers.append("no active or open checking account")
    if not qualifying_ids:
        savings_blockers.append("no active checking relationship open for at least 14 days")
    if len(savings) >= 5:
        savings_blockers.append("customer already has 5 or more savings accounts")
    if negative:
        savings_blockers.append("one or more accounts has a negative balance")
    if collections_found:
        savings_blockers.append("one or more accounts is in collections")
    if balance_unknown:
        savings_review.append("one or more account balances are unavailable or invalid")
    if collections_unknown:
        savings_review.append("collections status is unavailable for one or more accounts")

    checking_blockers, checking_review = [], []
    if payload.get("identity_verified") is not True:
        checking_blockers.append("customer identity is not verified")
    age = payload.get("age_years")
    if isinstance(age, bool) or not isinstance(age, (int, float)):
        checking_review.append("customer age is unknown")
    elif age < 18:
        checking_blockers.append("customer is younger than 18")
    if len(checking) >= 4:
        checking_blockers.append("customer already has 4 or more checking accounts")
    closed_for_cause = payload.get("checking_closed_for_cause_last_6_months")
    if closed_for_cause is True:
        checking_blockers.append("a checking account was closed for cause in the last 6 months")
    elif closed_for_cause is not False:
        checking_review.append("checking closure-for-cause history is unknown")

    return {
        "as_of": as_of.isoformat(),
        "counts": {"checking": len(checking), "savings": len(savings)},
        "qualifying_checking_account_ids": qualifying_ids,
        "checking": {"eligible": not checking_blockers and not checking_review,
                     "blockers": checking_blockers, "review_items": checking_review},
        "savings": {"eligible": not savings_blockers and not savings_review,
                    "blockers": savings_blockers, "review_items": savings_review},
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
