#!/usr/bin/env python3
"""Evaluate documented personal-checking opening prerequisites from JSON stdin."""

import json
import re
import sys
from datetime import date


def emit(value):
    json.dump(value, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def parse_date(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string date")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            from datetime import datetime
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError(f"{field_name} must use YYYY-MM-DD or MM/DD/YYYY")


def age_on_date(birth_date, current_date):
    return current_date.year - birth_date.year - (
        (current_date.month, current_date.day) < (birth_date.month, birth_date.day)
    )


def is_boolean(value):
    return isinstance(value, bool)


def main(payload):
    required = [
        "current_date",
        "date_of_birth",
        "identity_verified",
        "closure_for_cause_in_last_6_months",
        "accounts_complete",
        "accounts",
        "account_class",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        return {
            "eligible": None,
            "next_action": "do_not_open",
            "blocking_reasons": ["Missing required input: " + ", ".join(missing)],
            "checks": {},
        }

    try:
        today = parse_date(payload["current_date"], "current_date")
        dob = parse_date(payload["date_of_birth"], "date_of_birth")
    except ValueError as exc:
        return {
            "eligible": None,
            "next_action": "do_not_open",
            "blocking_reasons": [str(exc)],
            "checks": {},
        }

    if dob > today:
        return {
            "eligible": None,
            "next_action": "do_not_open",
            "blocking_reasons": ["date_of_birth cannot be in the future"],
            "checks": {},
        }

    boolean_fields = [
        "identity_verified",
        "closure_for_cause_in_last_6_months",
        "accounts_complete",
    ]
    non_boolean = [key for key in boolean_fields if not is_boolean(payload[key])]
    if non_boolean:
        return {
            "eligible": None,
            "next_action": "do_not_open",
            "blocking_reasons": ["Boolean required for: " + ", ".join(non_boolean)],
            "checks": {},
        }

    accounts = payload["accounts"]
    if not isinstance(accounts, list):
        return {
            "eligible": None,
            "next_action": "do_not_open",
            "blocking_reasons": ["accounts must be an array"],
            "checks": {},
        }

    invalid_accounts = []
    count = 0
    for index, account in enumerate(accounts):
        if not isinstance(account, dict) or not is_boolean(
            account.get("counts_toward_personal_checking_limit")
        ):
            invalid_accounts.append(index)
        elif account["counts_toward_personal_checking_limit"]:
            count += 1

    account_class = payload["account_class"]
    class_has_official_shape = (
        isinstance(account_class, str)
        and bool(account_class.strip())
        and bool(re.search(r"\bAccount\s*$", account_class))
    )

    approved_list = payload.get("official_account_classes")
    approved_class = True
    if approved_list is not None:
        if not isinstance(approved_list, list) or not all(
            isinstance(item, str) for item in approved_list
        ):
            return {
                "eligible": None,
                "next_action": "do_not_open",
                "blocking_reasons": ["official_account_classes must be an array of strings"],
                "checks": {},
            }
        approved_class = account_class in approved_list

    age = age_on_date(dob, today)
    checks = {
        "identity_verified": payload["identity_verified"],
        "minimum_age_18": age >= 18,
        "accounts_lookup_complete": payload["accounts_complete"],
        "account_records_normalized": not invalid_accounts,
        "under_personal_checking_limit_before_opening": count < 4,
        "under_personal_checking_limit_after_opening": count + 1 <= 4,
        "no_recent_checking_closure_for_cause": not payload[
            "closure_for_cause_in_last_6_months"
        ],
        "account_class_ends_with_account": class_has_official_shape,
        "account_class_is_approved_when_list_supplied": approved_class,
    }

    reasons = []
    if not checks["identity_verified"]:
        reasons.append("Identity verification and its audit record are required.")
    if not checks["minimum_age_18"]:
        reasons.append("Customer must be at least 18 years old.")
    if not checks["accounts_lookup_complete"]:
        reasons.append("A complete current account lookup is required.")
    if invalid_accounts:
        reasons.append(
            "Account records require an explicit personal-checking count classification: "
            + ", ".join(str(index) for index in invalid_accounts)
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
        "personal_checking_count": count,
        "new_total_personal_checking_count": count + 1,
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
        emit(
            {
                "eligible": None,
                "next_action": "do_not_open",
                "blocking_reasons": [str(exc)],
                "checks": {},
            }
        )


if __name__ == "__main__":
    run()
