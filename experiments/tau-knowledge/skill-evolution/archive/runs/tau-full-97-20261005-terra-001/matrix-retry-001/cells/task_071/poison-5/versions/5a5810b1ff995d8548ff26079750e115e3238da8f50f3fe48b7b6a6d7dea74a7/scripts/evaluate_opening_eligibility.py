#!/usr/bin/env python3
"""Evaluate supplied evidence for business account-opening prerequisites.

Input and output are JSON objects on stdin/stdout. This script is advisory only: it does
not retrieve account data, verify identity, open an account, or transfer funds.
"""
import json
import sys


def outcome(requirement, supplied, predicate, detail):
    if supplied is None:
        return {"requirement": requirement, "state": "unknown", "detail": detail}
    if predicate(supplied):
        return {"requirement": requirement, "state": "pass", "detail": detail}
    return {"requirement": requirement, "state": "fail", "detail": detail, "observed": supplied}


def total(checks):
    states = [check["state"] for check in checks]
    if "fail" in states:
        return False
    return None if "unknown" in states else True


def numeric_list(value, field):
    if value is None:
        return None
    if not isinstance(value, list) or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in value):
        raise ValueError(f"{field} must be an array of numeric integer-cent balances")
    return value


def checking(data):
    balances = numeric_list(data.get("open_personal_checking_balances"), "open_personal_checking_balances")
    qualifying = None if balances is None else any(balance >= 50000 for balance in balances)
    return [
        outcome("identity_verified", data.get("identity_verified"), lambda value: value is True, "Customer identity must be verified."),
        outcome("open_personal_checking", qualifying, lambda value: value is True, "At least one existing personal checking account must be OPEN."),
        outcome("business_checking_count", data.get("current_business_checking_count"), lambda value: isinstance(value, int) and not isinstance(value, bool) and value <= 6, "Customer must not exceed 6 business checking accounts."),
        outcome("no_closed_accounts", data.get("has_closed_accounts"), lambda value: value is False, "Customer must have no accounts with CLOSED status."),
        outcome("existing_checking_balance", qualifying, lambda value: value is True, "An existing checking account must have at least 50000 cents ($500)."),
    ], []


def savings(data):
    accounts = data.get("business_checking_accounts")
    if accounts is not None and not isinstance(accounts, list):
        raise ValueError("business_checking_accounts must be an array")
    has_open = None if accounts is None else False
    qualified = None if accounts is None else False
    source_ids = []
    if accounts is not None:
        for account in accounts:
            if not isinstance(account, dict):
                raise ValueError("each business_checking_accounts item must be an object")
            if account.get("status") != "OPEN":
                continue
            has_open = True
            age, balance = account.get("age_days"), account.get("balance")
            if isinstance(age, bool) or not isinstance(age, (int, float)) or isinstance(balance, bool) or not isinstance(balance, (int, float)):
                continue
            if age >= 30 and balance >= 250000:
                qualified = True
                if isinstance(account.get("account_id"), str):
                    source_ids.append(account["account_id"])
    return [
        outcome("identity_verified", data.get("identity_verified"), lambda value: value is True, "Customer identity must be verified."),
        outcome("open_business_checking", has_open, lambda value: value is True, "At least one business checking account must be OPEN."),
        outcome("business_savings_count", data.get("current_business_savings_count"), lambda value: isinstance(value, int) and not isinstance(value, bool) and value < 4, "Customer must have fewer than 4 business savings accounts."),
        outcome("no_negative_balances", data.get("has_negative_balance"), lambda value: value is False, "Customer must have no accounts with negative balances."),
        outcome("qualifying_business_checking", qualified, lambda value: value is True, "An OPEN business checking account must be at least 30 days old and hold at least 250000 cents ($2,500)."),
    ], source_ids


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    kind = data.get("account_kind")
    if kind == "checking":
        checks, source_ids = checking(data)
    elif kind == "savings":
        checks, source_ids = savings(data)
    else:
        raise ValueError("account_kind must be 'checking' or 'savings'")
    return {
        "account_kind": kind,
        "eligible": total(checks),
        "checks": checks,
        "qualifying_business_checking_source_ids": source_ids,
        "not_evaluated": [
            "customer authority", "account ownership", "exact official account class confirmation",
            "fees, limits, cutoffs, recipient details, and confirmation requirements",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
