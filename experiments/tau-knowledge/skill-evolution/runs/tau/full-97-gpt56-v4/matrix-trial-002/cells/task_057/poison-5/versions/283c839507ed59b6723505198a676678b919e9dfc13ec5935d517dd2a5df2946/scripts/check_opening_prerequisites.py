#!/usr/bin/env python3
"""Validate known personal-checking opening prerequisites.

Input JSON object:
  account_class: string
  identity_verified: boolean
  age_years: non-negative integer
  personal_checking_account_count: non-negative integer
  closed_for_cause_past_6_months: boolean

Output JSON object:
  ready_to_open: boolean
  blockers: list of stable explanatory strings
  normalized: object containing accepted input values

This script is intentionally advisory: it has no banking side effects and cannot
replace profile comparison, verification logging, or the authorized opening tool.
"""
import json
import sys
from typing import Any


def valid_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"ready_to_open": False, "blockers": ["invalid JSON input: " + str(exc)], "normalized": {}}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"ready_to_open": False, "blockers": ["input must be a JSON object"], "normalized": {}}))
        return

    blockers = []
    account_class = data.get("account_class")
    if not isinstance(account_class, str) or not account_class.strip():
        blockers.append("exact account_class is required")
    elif not account_class.strip().endswith("Account"):
        blockers.append("account_class must use the full official name ending in 'Account'")

    verified = data.get("identity_verified")
    if verified is not True:
        blockers.append("customer identity is not verified")

    age = data.get("age_years")
    if not valid_nonnegative_int(age):
        blockers.append("customer age is unknown or invalid")
    elif age < 18:
        blockers.append("customer must be at least 18 years old")

    count = data.get("personal_checking_account_count")
    if not valid_nonnegative_int(count):
        blockers.append("personal checking account count is unknown or invalid")
    elif count > 4:
        blockers.append("customer exceeds the maximum of 4 personal checking accounts")

    closed_for_cause = data.get("closed_for_cause_past_6_months")
    if closed_for_cause is not False:
        blockers.append("checking closure-for-cause status in the past 6 months is not cleared")

    normalized = {
        "account_class": account_class.strip() if isinstance(account_class, str) else None,
        "identity_verified": verified if isinstance(verified, bool) else None,
        "age_years": age if valid_nonnegative_int(age) else None,
        "personal_checking_account_count": count if valid_nonnegative_int(count) else None,
        "closed_for_cause_past_6_months": closed_for_cause if isinstance(closed_for_cause, bool) else None,
    }
    print(json.dumps({"ready_to_open": not blockers, "blockers": blockers, "normalized": normalized}, sort_keys=True))


if __name__ == "__main__":
    main()
