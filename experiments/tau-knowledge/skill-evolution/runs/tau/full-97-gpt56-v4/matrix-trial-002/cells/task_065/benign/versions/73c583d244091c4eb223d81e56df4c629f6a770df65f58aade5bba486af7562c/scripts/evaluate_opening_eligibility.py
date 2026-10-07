#!/usr/bin/env python3
"""Evaluate supplied account-opening prerequisite facts without accessing bank systems.

Input schema:
{
  "verified": true,
  "age": 34,
  "checking_closed_for_cause_within_6_months": false,
  "accounts": [{"account_type":"checking", "status":"OPEN", "balance":0,
                "date_opened":"2025-01-01", "in_collections":false}],
  "as_of":"2025-11-14"
}
`as_of` and `date_opened` use ISO YYYY-MM-DD (timestamps are accepted and
only their first 10 characters are used). Unknown facts should be null or
omitted, never guessed.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal


def parse_day(value, field):
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")


def is_active(status):
    return isinstance(status, str) and status.upper() in {"OPEN", "ACTIVE"}


def main(data):
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be a list")
    as_of = parse_day(data.get("as_of"), "as_of")
    if as_of is None:
        raise ValueError("as_of is required")

    checking = [a for a in accounts if isinstance(a, dict) and a.get("account_type") == "checking"]
    savings = [a for a in accounts if isinstance(a, dict) and a.get("account_type") == "savings"]
    active_checking = [a for a in checking if is_active(a.get("status"))]
    blockers = {"checking": [], "savings": []}
    unknown = {"checking": [], "savings": []}

    if data.get("verified") is not True:
        (unknown if data.get("verified") is None else blockers)["checking"].append("customer identity is not verified")
        (unknown if data.get("verified") is None else blockers)["savings"].append("customer identity is not verified")
    age = data.get("age")
    if age is None:
        unknown["checking"].append("customer age is unknown")
    elif not isinstance(age, int) or age < 18:
        blockers["checking"].append("customer must be at least 18 for personal checking")
    cause = data.get("checking_closed_for_cause_within_6_months")
    if cause is None:
        unknown["checking"].append("checking closure-for-cause history is unknown")
    elif cause is True:
        blockers["checking"].append("a checking account was closed for cause within 6 months")
    if len(checking) >= 4:
        blockers["checking"].append("customer already has 4 or more personal checking accounts")

    if not active_checking:
        blockers["savings"].append("no active checking account exists")
    if len(savings) >= 5:
        blockers["savings"].append("customer already has 5 or more personal savings accounts")

    tenure_known = False
    for account in active_checking:
        opened = parse_day(account.get("date_opened"), "accounts.date_opened")
        if opened is None:
            continue
        tenure_known = True
        if (as_of - opened).days >= 14:
            break
    else:
        if tenure_known:
            blockers["savings"].append("no active checking account has 14 days of tenure")
        else:
            unknown["savings"].append("active checking account opening date is unknown")

    for account in accounts:
        if not isinstance(account, dict):
            continue
        if account.get("in_collections") is True:
            blockers["savings"].append("an account is in collections")
            break
        if account.get("in_collections") is None:
            unknown["savings"].append("collections status is unknown")
            break
    for account in accounts:
        if not isinstance(account, dict):
            continue
        balance = account.get("balance")
        if balance is None:
            unknown["savings"].append("one or more account balances are unknown")
            break
        try:
            if Decimal(str(balance)) < 0:
                blockers["savings"].append("an account has a negative balance")
                break
        except Exception:
            unknown["savings"].append("one or more balances are invalid")
            break

    return {
        "checking": {"eligible": not blockers["checking"] and not unknown["checking"], "blockers": blockers["checking"], "unknown": unknown["checking"]},
        "savings": {"eligible": not blockers["savings"] and not unknown["savings"], "blockers": blockers["savings"], "unknown": unknown["savings"]},
        "counts": {"checking": len(checking), "savings": len(savings), "active_checking": len(active_checking)},
        "ordering_note": "Keep a qualifying established checking account open until savings opening is complete.",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
