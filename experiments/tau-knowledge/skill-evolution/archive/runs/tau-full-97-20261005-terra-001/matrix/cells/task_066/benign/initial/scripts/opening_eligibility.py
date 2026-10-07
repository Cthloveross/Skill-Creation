#!/usr/bin/env python3
"""Check deterministic published checking and savings opening conditions."""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

def date_value(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            pass
    return None

def nonnegative(value):
    try:
        return Decimal(str(value)) >= 0
    except (InvalidOperation, ValueError):
        return None

def active_or_open(account):
    return str(account.get("status", "")).upper() in {"ACTIVE", "OPEN"}

def result(blockers, unresolved):
    return {"eligible": not blockers and not unresolved, "blockers": blockers, "unresolved": unresolved}

def main(data):
    accounts = data.get("accounts") or []
    today = date_value(data.get("as_of"))
    verified = data.get("verified")
    age = data.get("age")
    checking_accounts = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    savings_accounts = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]

    cb, cu = [], []
    if verified is not True:
        (cb if verified is False else cu).append("Identity verification must be completed.")
    if age is None:
        cu.append("Customer age is required for checking opening.")
    elif age < 18:
        cb.append("Customer must be at least 18 to open personal checking.")
    if len(checking_accounts) >= 4:
        cb.append("Customer already has the maximum of four personal checking accounts.")
    closed_cause = data.get("checking_closed_for_cause_last_6_months")
    if closed_cause is True:
        cb.append("A checking account was closed for cause within the last six months.")
    elif closed_cause is None:
        cu.append("Checking closure-for-cause history for the preceding six months is required.")

    sb, su = [], []
    if verified is not True:
        (sb if verified is False else su).append("Identity verification must be completed.")
    eligible_checking = [a for a in checking_accounts if active_or_open(a)]
    if not eligible_checking:
        sb.append("An active Rho-Bank checking account is required for savings opening.")
    if len(savings_accounts) >= 5:
        sb.append("Customer already has the maximum of five personal savings accounts.")
    for account in accounts:
        status = str(account.get("status", "")).upper()
        balance_ok = nonnegative(account.get("balance"))
        if status == "COLLECTIONS":
            sb.append("Accounts in collections must be resolved before savings opening.")
            break
        if balance_ok is False:
            sb.append("Negative balances must be resolved before savings opening.")
            break
        if balance_ok is None:
            su.append("All account balances are required to check for negative balances.")
            break
    if today is None:
        su.append("Current date is required to evaluate checking tenure.")
    else:
        dates = [date_value(a.get("date_opened")) for a in eligible_checking]
        if not dates or any(d is None for d in dates):
            su.append("Opening date for an active checking account is required.")
        elif max((today - d).days for d in dates) < 14:
            sb.append("At least one active checking account must have been held for 14 days.")
    return {"checking": result(cb, cu), "savings": result(sb, su)}

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
