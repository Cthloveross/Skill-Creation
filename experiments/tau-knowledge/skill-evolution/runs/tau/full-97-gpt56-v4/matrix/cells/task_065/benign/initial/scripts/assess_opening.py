#!/usr/bin/env python3
"""Evaluate documented checking and savings opening prerequisites.

Reads one JSON object from stdin and writes a JSON report to stdout. This program
is advisory only; it neither reads bank systems nor initiates bank operations.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    candidates = ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z")
    for fmt in candidates:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def as_money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def main(payload):
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        accounts = []
        accounts_supplied = False
    else:
        accounts_supplied = True

    now = parse_date(payload.get("now"))
    dob = parse_date(payload.get("date_of_birth"))
    verified = payload.get("identity_verified") is True
    age_ok = None
    if now and dob:
        age_ok = (now.year - dob.year - ((now.month, now.day) < (dob.month, dob.day))) >= 18

    checking = [a for a in accounts if isinstance(a, dict) and str(a.get("account_type", "")).lower() == "checking"]
    savings = [a for a in accounts if isinstance(a, dict) and str(a.get("account_type", "")).lower() == "savings"]
    active_checking = [a for a in checking if str(a.get("status", "")).upper() in {"OPEN", "ACTIVE"}]

    tenure_ok = False
    tenure_known = False
    if now:
        for account in active_checking:
            opened = parse_date(account.get("date_opened"))
            if opened:
                tenure_known = True
                if (now - opened).days >= 14:
                    tenure_ok = True
                    break

    balance_known = True
    no_negative = True
    no_collections = True
    for account in accounts:
        if not isinstance(account, dict):
            balance_known = False
            no_negative = False
            no_collections = False
            continue
        balance = as_money(account.get("balance"))
        if balance is None:
            balance_known = False
            no_negative = False
        elif balance < 0:
            no_negative = False
        if str(account.get("status", "")).upper() == "COLLECTIONS":
            no_collections = False

    closure_history = payload.get("checking_closed_for_cause_within_6_months")
    no_bad_closure = False if closure_history is True else (True if closure_history is False else None)

    checking_checks = {
        "identity_verified": verified,
        "age_at_least_18": age_ok,
        "fewer_than_four_checking_accounts": len(checking) < 4 if accounts_supplied else None,
        "no_checking_closed_for_cause_within_6_months": no_bad_closure,
    }
    savings_checks = {
        "identity_verified": verified,
        "active_checking_exists": len(active_checking) > 0 if accounts_supplied else None,
        "a_checking_has_at_least_14_days_tenure": tenure_ok if tenure_known else None,
        "fewer_than_five_savings_accounts": len(savings) < 5 if accounts_supplied else None,
        "no_negative_balances": no_negative if balance_known else None,
        "no_accounts_in_collections": no_collections if accounts_supplied else None,
    }

    def eligible(checks):
        return all(value is True for value in checks.values())

    blockers = []
    for category, checks in (("checking", checking_checks), ("savings", savings_checks)):
        for key, value in checks.items():
            if value is not True:
                prefix = "unknown" if value is None else "failed"
                blockers.append(f"{category}: {prefix} prerequisite {key}")

    return {
        "checking_eligible": eligible(checking_checks),
        "savings_eligible": eligible(savings_checks),
        "checking_checks": checking_checks,
        "savings_checks": savings_checks,
        "counts": {"checking": len(checking), "savings": len(savings)},
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "checking_eligible": False, "savings_eligible": False}))
        sys.exit(2)
