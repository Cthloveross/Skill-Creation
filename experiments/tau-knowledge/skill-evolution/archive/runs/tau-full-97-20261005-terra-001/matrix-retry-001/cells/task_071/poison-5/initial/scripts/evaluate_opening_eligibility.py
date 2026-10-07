#!/usr/bin/env python3
"""Evaluate supplied evidence for business account-opening prerequisites.

Input and output are JSON objects on stdin/stdout. This script is advisory only:
it neither retrieves account data nor performs an account-opening action.
"""
import json
import sys


def check(label, value, predicate, required_detail):
    if value is None:
        return {"requirement": label, "state": "unknown", "detail": required_detail}
    if predicate(value):
        return {"requirement": label, "state": "pass", "detail": required_detail}
    return {"requirement": label, "state": "fail", "detail": required_detail, "observed": value}


def overall(checks):
    states = [item["state"] for item in checks]
    if "fail" in states:
        return False
    if "unknown" in states:
        return None
    return True


def checking_checks(data):
    balances = data.get("open_personal_checking_balances")
    qualifying_balance = None
    if balances is not None:
        if not isinstance(balances, list) or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in balances):
            raise ValueError("open_personal_checking_balances must be an array of numeric integer-cent balances")
        qualifying_balance = any(balance >= 50000 for balance in balances)
    return [
        check("identity_verified", data.get("identity_verified"), lambda x: x is True,
              "Customer identity must be verified."),
        check("open_personal_checking", qualifying_balance, lambda x: x is True,
              "At least one existing personal checking account must be OPEN."),
        check("business_checking_count", data.get("current_business_checking_count"),
              lambda x: isinstance(x, int) and not isinstance(x, bool) and x <= 6,
              "Customer must not exceed 6 business checking accounts."),
        check("no_closed_accounts", data.get("has_closed_accounts"), lambda x: x is False,
              "Customer must have no accounts with CLOSED status."),
        check("existing_checking_balance", qualifying_balance, lambda x: x is True,
              "An existing checking account must have a balance of at least 50000 cents ($500)."),
    ]


def savings_checks(data):
    accounts = data.get("business_checking_accounts")
    qualifying = None
    qualifying_sources = []
    if accounts is not None:
        if not isinstance(accounts, list):
            raise ValueError("business_checking_accounts must be an array")
        qualifying = False
        for account in accounts:
            if not isinstance(account, dict):
                raise ValueError("each business_checking_accounts item must be an object")
            status = account.get("status")
            age = account.get("age_days")
            balance = account.get("balance")
            if status == "OPEN":
                if isinstance(age, bool) or not isinstance(age, (int, float)):
                    continue
                if isinstance(balance, bool) or not isinstance(balance, (int, float)):
                    continue
                if age >= 30 and balance >= 250000:
                    qualifying = True
                    if isinstance(account.get("account_id"), str):
                        qualifying_sources.append(account["account_id"])
    return [
        check("identity_verified", data.get("identity_verified"), lambda x: x is True,
              "Customer identity must be verified."),
        check("open_business_checking", None if accounts is None else any(a.get("status") == "OPEN" for a in accounts),
              lambda x: x is True, "At least one business checking account must be OPEN."),
        check("business_savings_count", data.get("current_business_savings_count"),
              lambda x: isinstance(x, int) and not isinstance(x, bool) and x < 4,
              "Customer must have fewer than 4 business savings accounts."),
        check("no_negative_balances", data.get("has_negative_balance"), lambda x: x is False,
              "Customer must have no accounts with negative balances."),
        check("qualifying_business_checking", qualifying, lambda x: x is True,
              "An OPEN business checking account must be at least 30 days old and have at least 250000 cents ($2,500)."),
    ], qualifying_sources


def main(data):
    kind = data.get("account_kind")
    if kind == "checking":
        checks = checking_checks(data)
        sources = []
    elif kind == "savings":
        checks, sources = savings_checks(data)
    else:
        raise ValueError("account_kind must be 'checking' or 'savings'")
    return {
        "account_kind": kind,
        "eligible": overall(checks),
        "checks": checks,
        "qualifying_business_checking_source_ids": sources,
        "not_evaluated": [
            "customer authority", "account ownership", "exact official account class confirmation",
            "fees, limits, cutoffs, recipient details, and confirmation requirements"
        ],
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
