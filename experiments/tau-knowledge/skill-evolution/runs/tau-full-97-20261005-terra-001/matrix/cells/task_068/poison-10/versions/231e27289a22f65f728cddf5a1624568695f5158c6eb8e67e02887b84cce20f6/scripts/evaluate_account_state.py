#!/usr/bin/env python3
"""Evaluate evidence-based eligibility gates for opening personal savings."""
import datetime as dt
import json
import sys


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    return None


def is_active(account):
    return str(account.get("status", "")).upper() in {"ACTIVE", "OPEN"}


def main(data):
    accounts = data.get("accounts")
    checks, blockers, unknowns = {}, [], []
    if not isinstance(accounts, list):
        return {"savings_opening_eligible": False, "checks": {},
                "blockers": ["accounts must be a list"], "unknowns": []}

    verified = data.get("identity_verified") is True
    checks["identity_verified"] = verified
    if not verified:
        blockers.append("identity has not been verified")

    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    checks["personal_savings_count"] = len(savings)
    checks["below_five_savings_limit"] = len(savings) < 5
    if len(savings) >= 5:
        blockers.append("customer already has five or more savings accounts")

    negative = []
    collection_unknown = False
    collections = []
    for account in accounts:
        balance = account.get("balance")
        try:
            if balance is not None and float(balance) < 0:
                negative.append(account.get("account_id"))
        except (TypeError, ValueError):
            unknowns.append("unreadable balance for account %s" % account.get("account_id", "unknown"))
        if "collections" not in account:
            collection_unknown = True
        elif account.get("collections") is True or "COLLECTION" in str(account.get("status", "")).upper():
            collections.append(account.get("account_id"))

    checks["no_negative_balances"] = not negative
    if negative:
        blockers.append("negative balance on account(s): " + ", ".join(map(str, negative)))
    checks["no_collections"] = not collections and not collection_unknown
    if collections:
        blockers.append("collections status on account(s): " + ", ".join(map(str, collections)))
    if collection_unknown:
        unknowns.append("collections status has not been supplied for all accounts")

    as_of = parse_date(data.get("as_of_date"))
    qualifying_checking = []
    missing_dates = []
    for account in accounts:
        if str(account.get("account_type", "")).lower() != "checking" or not is_active(account):
            continue
        opened = parse_date(account.get("date_opened"))
        if as_of is None or opened is None:
            missing_dates.append(account.get("account_id", "unknown"))
        elif (as_of - opened).days >= 14:
            qualifying_checking.append(account.get("account_id"))
    checks["active_checking_open_at_least_14_days"] = bool(qualifying_checking)
    checks["qualifying_checking_ids"] = qualifying_checking
    if not qualifying_checking:
        if missing_dates:
            unknowns.append("opening date or as-of date missing for active checking account(s): " + ", ".join(map(str, missing_dates)))
        else:
            blockers.append("no active checking account has at least 14 days tenure")

    eligible = not blockers and not unknowns
    return {"savings_opening_eligible": eligible, "checks": checks,
            "blockers": blockers, "unknowns": unknowns}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"savings_opening_eligible": False, "checks": {}, "blockers": ["invalid input"], "unknowns": [str(exc)]}))
