#!/usr/bin/env python3
"""Assess explicit personal-checking opening gates from JSON stdin.

This program is deliberately read-only. It accepts a JSON object described in
SKILL.md and writes one JSON assessment to stdout.
"""
import datetime as dt
import json
import sys


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def age_on(dob, today):
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return years


def is_personal_checking(account):
    if not isinstance(account, dict):
        return False, True
    personal = account.get("personal")
    acct_type = str(account.get("account_type", "")).strip().lower()
    acct_class = str(account.get("account_class", "")).strip().lower()
    checking = "checking" in acct_type or "checking" in acct_class
    if not checking:
        return False, False
    if personal is False:
        return False, False
    # Returned accounts are for the authenticated user; missing personal is
    # provisionally counted but highlighted because account type can be unclear.
    return True, personal is None


def main(data):
    blocking = []
    unknown = []
    warnings = []

    dob = parse_date(data.get("date_of_birth"))
    as_of = parse_date(data.get("as_of_date"))
    age = None
    if dob is None or as_of is None:
        unknown.append("valid date_of_birth and as_of_date are required to verify age")
    else:
        age = age_on(dob, as_of)
        if age < 18:
            blocking.append("customer is under 18")

    if data.get("identity_verified") is not True:
        unknown.append("identity has not been verified with two confirmed profile fields")
    if data.get("verification_logged") is not True:
        unknown.append("successful identity verification has not been logged")

    raw_accounts = data.get("accounts")
    count = None
    if not isinstance(raw_accounts, list):
        unknown.append("current account records are unavailable")
    else:
        count = 0
        ambiguous = False
        for account in raw_accounts:
            included, unclear = is_personal_checking(account)
            if included:
                count += 1
            ambiguous = ambiguous or unclear
        if ambiguous:
            warnings.append("one or more checking records lack explicit personal classification; confirm classification")
        if count > 4:
            blocking.append("customer exceeds four personal checking accounts")

    closure = data.get("closed_for_cause_within_six_months", None)
    if closure is True:
        blocking.append("a checking account was closed for cause within the prior six months")
    elif closure is not False:
        unknown.append("checking closure-for-cause history for the prior six months is unknown")

    account_class = data.get("account_class")
    if not isinstance(account_class, str) or not account_class.strip():
        unknown.append("desired official account_class is missing")
    elif not account_class.strip().endswith("Account"):
        blocking.append("personal checking account_class must use the full official name ending in 'Account'")

    if data.get("customer_authorized") is not True:
        unknown.append("customer has not provided unambiguous authorization to open the selected account")

    eligible = False if blocking else (None if unknown else True)
    return {
        "eligible": eligible,
        "age": age,
        "personal_checking_count": count,
        "blocking_reasons": blocking,
        "unknown_requirements": unknown,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": None, "error": str(exc)}))
        sys.exit(1)
