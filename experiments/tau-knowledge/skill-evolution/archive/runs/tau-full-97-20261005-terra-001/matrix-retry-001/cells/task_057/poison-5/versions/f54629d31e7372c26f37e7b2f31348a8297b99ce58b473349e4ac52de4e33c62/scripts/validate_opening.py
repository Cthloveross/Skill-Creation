#!/usr/bin/env python3
"""Assess whether required personal-checking opening facts are complete and passing.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs no
identity lookup, date calculation, account retrieval, tool invocation, or account opening.
"""
import json
import sys


def known_bool(value):
    return value if isinstance(value, bool) else None


def main(record):
    if not isinstance(record, dict):
        return {"error": "top-level JSON value must be an object"}

    checks = {}
    blocks = []

    for field, label in (
        ("identity_verified", "identity verification"),
        ("customer_authorized", "customer authority"),
        ("account_class_confirmed", "exact account-class confirmation"),
        ("official_personal_checking_class", "official personal checking class"),
    ):
        value = known_bool(record.get(field))
        checks[field] = value
        if value is not True:
            blocks.append(f"{label} is not confirmed")

    age = record.get("age_years")
    if isinstance(age, bool) or not isinstance(age, int):
        checks["age_18_or_older"] = None
        blocks.append("verified age is unavailable")
    else:
        checks["age_18_or_older"] = age >= 18
        if age < 18:
            blocks.append("customer is under 18")

    count = record.get("existing_personal_checking_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        checks["new_account_within_four_account_limit"] = None
        blocks.append("current personal checking account count is unavailable")
    else:
        checks["new_account_within_four_account_limit"] = count < 4
        if count >= 4:
            blocks.append("opening another account would exceed four personal checking accounts")

    history_verified = known_bool(record.get("closure_history_verified"))
    closed_for_cause = known_bool(record.get("closure_for_cause_last_6_months"))
    if history_verified is not True:
        checks["no_recent_closure_for_cause"] = None
        blocks.append("closure-for-cause history for the last six months is not verified")
    elif closed_for_cause is None:
        checks["no_recent_closure_for_cause"] = None
        blocks.append("closure-for-cause result is unavailable")
    else:
        checks["no_recent_closure_for_cause"] = not closed_for_cause
        if closed_for_cause:
            blocks.append("a checking account was closed for cause within the last six months")

    return {
        "ready_to_open": not blocks,
        "checks": checks,
        "blocking_reasons": blocks,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc}"}, sort_keys=True))
