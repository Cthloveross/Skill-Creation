#!/usr/bin/env python3
"""Read-only prerequisite evaluator for checking closure and savings opening.

Reads one JSON object from stdin and writes one JSON object to stdout.  It does
not access services or perform banking actions.
"""
import json
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def class_key(value):
    return " ".join(str(value or "").lower().split())


def is_green_checking(account):
    key = class_key(account.get("account_class"))
    return key in {"green account", "green account (checking)"} and class_key(account.get("account_type")) == "checking"


def is_savings(account):
    return class_key(account.get("account_type")) == "savings"


def is_active_checking(account):
    return (class_key(account.get("account_type")) == "checking" and
            class_key(account.get("status")) in {"active", "open"})


def item(name, passed, detail):
    return {"requirement": name, "passed": passed, "detail": detail}


def main(data):
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        return {"invalid_input": True, "error": "accounts must be a JSON array"}

    now = parse_date(data.get("now"))
    verified = data.get("identity_verified") is True
    opening_checks = [item("identity verification logged", verified,
                          "Set identity_verified true only after successful two-field verification and logging.")]

    active_checking = [a for a in accounts if is_active_checking(a)]
    opening_checks.append(item("active checking account exists", bool(active_checking),
                               "At least one checking account must be ACTIVE or OPEN."))

    tenure_known = bool(active_checking) and now is not None
    qualifying_tenure = False
    if tenure_known:
        for account in active_checking:
            opened = parse_date(account.get("date_opened"))
            if opened is not None and (now - opened).days >= 14:
                qualifying_tenure = True
                break
    tenure_detail = "Need a current date and date_opened for an active checking account."
    if qualifying_tenure:
        tenure_detail = "At least one active checking account is at least 14 days old."
    elif tenure_known:
        tenure_detail = "No active checking account is confirmed to be at least 14 days old."
    opening_checks.append(item("checking tenure at least 14 days", qualifying_tenure, tenure_detail))

    savings = [a for a in accounts if is_savings(a)]
    opening_checks.append(item("fewer than five personal savings accounts", len(savings) < 5,
                               "Found %d savings account record(s)." % len(savings)))

    negative_or_collection = []
    data_complete = True
    for account in accounts:
        bal = money(account.get("balance"))
        if bal is None or "in_collections" not in account:
            data_complete = False
        if bal is not None and bal < 0:
            negative_or_collection.append(account.get("account_id", "unknown account") + " has a negative balance")
        if account.get("in_collections") is True:
            negative_or_collection.append(account.get("account_id", "unknown account") + " is in collections")
    good_standing = data_complete and not negative_or_collection
    standing_detail = "All account balances and collections flags are required."
    if data_complete:
        standing_detail = "No negative balance or collections flag found." if good_standing else "; ".join(negative_or_collection)
    opening_checks.append(item("no collections and no negative balances", good_standing, standing_detail))

    target = data.get("target_closure_class", "Green Account (checking)")
    target_key = class_key(target)
    if target_key in {"green account", "green account (checking)"}:
        candidates = [a for a in accounts if is_green_checking(a)]
    else:
        candidates = [a for a in accounts if class_key(a.get("account_class")) == target_key and class_key(a.get("account_type")) == "checking"]

    closure_checks = [item("exactly one requested checking account located", len(candidates) == 1,
                           "Found %d matching checking account(s)." % len(candidates))]
    earliest = None
    if len(candidates) == 1:
        account = candidates[0]
        closure_checks.append(item("account status is OPEN", class_key(account.get("status")) == "open",
                                   "Reported status: %s" % account.get("status", "missing")))
        txns = data.get("closure_transactions")
        if not isinstance(txns, list):
            closure_checks.append(item("no pending transactions", False, "Transaction history is required."))
        else:
            pending = [t for t in txns if class_key(t.get("status")) == "pending"]
            closure_checks.append(item("no pending transactions", not pending,
                                       "Found %d pending transaction(s)." % len(pending)))

        opened = parse_date(account.get("date_opened"))
        balance = money(account.get("balance"))
        if opened is None or now is None:
            closure_checks.append(item("Green 3-day notice and fee timing", False,
                                       "Current date and account opening date are required."))
            closure_checks.append(item("balance supports applicable closure fee", False,
                                       "Account balance, opening date, and current date are required."))
        else:
            earliest = opened + timedelta(days=3)
            notice_ok = now >= earliest
            age_days = (now - opened).days
            fee = Decimal("25.00") if age_days < 60 else Decimal("0.00")
            closure_checks.append(item("Green 3-day notice elapsed", notice_ok,
                                       "Earliest closure date is %s." % earliest.isoformat()))
            if balance is None:
                closure_checks.append(item("balance supports applicable closure fee", False,
                                           "Balance is missing; applicable fee is $%s." % fee))
            elif fee > 0:
                closure_checks.append(item("balance supports $25 early closure fee", balance >= fee,
                                           "Within 60 days; reported balance is $%s." % balance))
            else:
                closure_checks.append(item("zero balance after fee window", balance == 0,
                                           "No early fee applies; reported balance is $%s." % balance))
    else:
        closure_checks.append(item("closure prerequisites", False,
                                   "Resolve account selection before checking status, transactions, dates, or balance."))

    return {
        "invalid_input": False,
        "savings_opening": {"ready": all(x["passed"] for x in opening_checks), "checks": opening_checks},
        "checking_closure": {
            "target_class": target,
            "ready": all(x["passed"] for x in closure_checks),
            "earliest_closure_date": earliest.isoformat() if earliest else None,
            "checks": closure_checks
        },
        "important": "This assessment is read-only. It does not establish customer authorization or execute any action."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"invalid_input": True, "error": str(exc)}))
        sys.exit(1)
