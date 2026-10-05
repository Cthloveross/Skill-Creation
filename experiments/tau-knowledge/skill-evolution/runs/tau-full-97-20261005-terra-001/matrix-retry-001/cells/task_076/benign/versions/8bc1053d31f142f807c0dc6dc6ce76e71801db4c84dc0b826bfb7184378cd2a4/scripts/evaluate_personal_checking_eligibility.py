#!/usr/bin/env python3
"""Evaluate documented personal-checking opening prerequisites from JSON stdin."""

import json
import re
import sys
from datetime import datetime


def emit(value):
    json.dump(value, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def result_unknown(reason):
    return {
        "eligible": None,
        "next_action": "do_not_open",
        "blocking_reasons": [reason],
        "checks": {},
    }


def parse_date(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string date")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"{field_name} must use YYYY-MM-DD or MM/DD/YYYY")


def age_on_date(birth_date, current_date):
    return current_date.year - birth_date.year - (
        (current_date.month, current_date.day) < (birth_date.month, birth_date.day)
    )


def is_boolean(value):
    return isinstance(value, bool)


def main(payload):
    required = (
        "current_date",
        "date_of_birth",
        "identity_verified",
        "closure_for_cause_in_last_6_months",
        "accounts_complete",
        "accounts",
        "account_class",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        return result_unknown("Missing required input: " + ", ".join(missing))

    try:
        today = parse_date(payload["current_date"], "current_date")
        dob = parse_date(payload["date_of_birth"], "date_of_birth")
    except ValueError as exc:
        return result_unknown(str(exc))
    if dob > today:
        return result_unknown("date_of_birth cannot be in the future")

    boolean_fields = (
        "identity_verified",
        "closure_for_cause_in_last_6_months",
        "accounts_complete",
    )
    invalid_booleans = [key for key in boolean_fields if not is_boolean(payload[key])]
    if invalid_booleans:
        return result_unknown("Boolean required for: " + ", ".join(invalid_booleans))

    accounts = payload["accounts"]
    if not isinstance(accounts, list):
        return result_unknown("accounts must be an array")

    personal_checking_count = 0
    invalid_records = []
    for index, record in enumerate(accounts):
        if not isinstance(record, dict) or not is_boolean(
            record.get("counts_toward_personal_checking_limit")
        ):
            invalid_records.append(index)
        elif record["counts_toward_personal_checking_limit"]:
            personal_checking_count += 1

    account_class = payload["account_class"]
    class_has_official_shape = (
        isinstance(account_class, str)
        and bool(account_class.strip())
        and bool(re.search(r"\bAccount$", account_class))
    )

    approved_class = True
    approved_list = payload.get("official_account_classes")
    if approved_list is not None:
        if not isinstance(approved_list, list) or not all(
            isinstance(item, str) for item in approved_list
        ):
            return result_unknown("official_account_classes must be an array of strings")
        approved_class = account_class in approved_list

    age = age_on_date(dob, today)
    new_total = personal_checking_count + 1
    checks = {
        "identity_verified": payload["identity_verified"],
        "minimum_age_18": age >= 18,
        "accounts_lookup_complete": payload["accounts_complete"],
        "account_records_normalized": not invalid_records,
        "under_personal_checking_limit_before_opening": personal_checking_count < 4,
        "under_personal_checking_limit_after_opening": new_total <= 4,
        "no_recent_checking_closure_for_cause": not payload[
            "closure_for_cause_in_last_6_months"
        ],
        "account_class_ends_with_account": class_has_official_shape,
        "account_class_is_approved_when_list_supplied": approved_class,
    }

    reasons = []
    if not checks["identity_verified"]:
        reasons.append("Identity verification and a successful audit record are required.")
    if not checks["minimum_age_18"]:
        reasons.append("Customer must be at least 18 years old.")
    if not checks["accounts_lookup_complete"]:
        reasons.append("A complete current account lookup is required.")
    if invalid_records:
        reasons.append(
            "Every account record needs an explicit personal-checking count classification: "
            + ", ".join(str(index) for index in invalid_records)
        )
    if not checks["under_personal_checking_limit_after_opening"]:
        reasons.append("Opening would exceed the four personal checking account maximum.")
    if not checks["no_recent_checking_closure_for_cause"]:
        reasons.append("Customer has a checking account closed for cause within six months.")
    if not checks["account_class_ends_with_account"]:
        reasons.append("account_class must be the full official name ending with 'Account'.")
    if not checks["account_class_is_approved_when_list_supplied"]:
        reasons.append("account_class is not in the supplied approved account-class list.")

    eligible = not reasons
    return {
        "eligible": eligible,
        "next_action": "open_account" if eligible else "do_not_open",
        "age_years": age,
        "personal_checking_count": personal_checking_count,
        "new_total_personal_checking_count": new_total,
        "checks": checks,
        "blocking_reasons": reasons,
    }


def run():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON value must be an object")
        emit(main(payload))
    except (json.JSONDecodeError, ValueError) as exc:
        emit(result_unknown(str(exc)))


if __name__ == "__main__":
    run()
