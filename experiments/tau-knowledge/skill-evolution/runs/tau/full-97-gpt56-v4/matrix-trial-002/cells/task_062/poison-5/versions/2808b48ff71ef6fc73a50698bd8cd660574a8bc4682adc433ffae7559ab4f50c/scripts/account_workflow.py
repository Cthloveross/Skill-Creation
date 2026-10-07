#!/usr/bin/env python3
"""Assess account-opening or closure prerequisites from JSON supplied on stdin.

Input object:
  operation: business_opening | personal_savings_opening | closure
  now: ISO-8601 date/time (required for closure fee assessment)
  accounts: list of account objects. Expected fields are account_id, account_type,
            account_class, status, balance, date_opened. Optional fields are
            is_business, ownership_type, collections, pending_transactions.
  identity_verified: boolean (opening operations)
  target_account_id: string (closure)
  pending_transactions: boolean (closure; overrides target record when provided)

Output object has eligible, blockers, checks, and operation-specific values.
Unknown facts are deliberately reported as blockers rather than assumed true.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def as_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def amount(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def active_status(account):
    return str(account.get("status", "")).upper() in {"ACTIVE", "OPEN"}


def is_personal_checking(account):
    if str(account.get("account_type", "")).lower() != "checking":
        return False
    marker = account.get("is_business")
    if marker is not None:
        return marker is False
    ownership = str(account.get("ownership_type", "")).lower()
    return ownership in {"personal", "individual", "consumer"}


def is_business_checking(account):
    if str(account.get("account_type", "")).lower() != "checking":
        return False
    marker = account.get("is_business")
    if marker is not None:
        return marker is True
    return str(account.get("ownership_type", "")).lower() == "business"


def add_check(result, label, value, blocker):
    result["checks"][label] = value
    if value is not True:
        result["blockers"].append(blocker)


def personal_savings(accounts, verified, today):
    result = {"operation": "personal_savings_opening", "eligible": False,
              "checks": {}, "blockers": []}
    add_check(result, "identity_verified", verified is True,
              "Customer identity is not verified.")
    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking" and active_status(a)]
    add_check(result, "active_checking_exists", bool(checking),
              "No active checking account was found.")
    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings" and not is_business_checking(a)]
    under_limit = len(savings) < 5
    result["checks"]["personal_savings_count"] = len(savings)
    add_check(result, "under_personal_savings_limit", under_limit,
              "Customer already has five or more personal savings accounts.")
    balances_known = all(amount(a.get("balance")) is not None for a in accounts)
    no_negative = balances_known and all(amount(a.get("balance")) >= 0 for a in accounts)
    add_check(result, "no_negative_balances", no_negative,
              "Negative-balance status is unknown or at least one account has a negative balance.")
    collections_known = all("collections" in a for a in accounts)
    no_collections = collections_known and not any(bool(a.get("collections")) for a in accounts)
    add_check(result, "no_collections", no_collections,
              "Collections status is unknown or at least one account is in collections.")
    tenure_known = bool(checking) and today is not None and all(as_date(a.get("date_opened")) for a in checking)
    tenure_ok = tenure_known and any((today - as_date(a.get("date_opened"))).days >= 14 for a in checking)
    add_check(result, "checking_tenure_at_least_14_days", tenure_ok,
              "No active checking account with a verified tenure of at least 14 days was found.")
    result["eligible"] = not result["blockers"]
    return result


def business_opening(accounts, verified):
    result = {"operation": "business_opening", "eligible": False,
              "checks": {}, "blockers": []}
    add_check(result, "identity_verified", verified is True,
              "Customer identity is not verified.")
    personal = [a for a in accounts if is_personal_checking(a) and str(a.get("status", "")).upper() == "OPEN"]
    add_check(result, "open_personal_checking_exists", bool(personal),
              "No existing personal checking account with status OPEN was verified.")
    classification_known = all(("is_business" in a) or ("ownership_type" in a) for a in accounts if str(a.get("account_type", "")).lower() == "checking")
    business_count = len([a for a in accounts if is_business_checking(a)])
    result["checks"]["business_checking_count"] = business_count if classification_known else "unknown"
    add_check(result, "under_business_checking_limit", classification_known and business_count < 6,
              "Business-checking count is unknown or the six-account maximum has been reached.")
    no_closed = all(str(a.get("status", "")).upper() != "CLOSED" for a in accounts)
    add_check(result, "no_closed_accounts", no_closed,
              "At least one account has status CLOSED.")
    balances = [amount(a.get("balance")) for a in personal]
    balance_ok = bool(balances) and all(x is not None for x in balances) and any(x >= Decimal("500") for x in balances)
    add_check(result, "existing_checking_balance_at_least_500", balance_ok,
              "No verified existing personal checking balance of at least $500 was found.")
    result["eligible"] = not result["blockers"]
    return result


CLOSURE_RULES = {
    ("savings", "Bronze Account"): {"fee": Decimal("20"), "days": 60, "notice_days": 1},
    ("checking", "Evergreen Account"): {"fee": Decimal("50"), "days": 90, "notice_days": 7},
}


def closure(accounts, target_id, today, request):
    result = {"operation": "closure", "eligible": False, "checks": {}, "blockers": []}
    target = next((a for a in accounts if str(a.get("account_id")) == str(target_id)), None)
    if not target:
        result["blockers"].append("Target account was not found in the supplied account records.")
        return result
    result["target_account"] = {k: target.get(k) for k in ("account_id", "account_type", "account_class", "status", "balance", "date_opened")}
    add_check(result, "status_open", str(target.get("status", "")).upper() == "OPEN",
              "Target account status is not OPEN.")
    pending = request.get("pending_transactions", target.get("pending_transactions"))
    add_check(result, "no_pending_transactions", pending is False,
              "Pending-transaction state is unknown or transactions are pending.")
    rule = CLOSURE_RULES.get((str(target.get("account_type", "")).lower(), target.get("account_class")))
    if not rule:
        result["blockers"].append("No documented closure rule is available for this account type and class.")
        return result
    opened = as_date(target.get("date_opened"))
    if today is None or opened is None:
        result["blockers"].append("Current date or account opening date is unavailable for early-fee assessment.")
        return result
    age_days = (today - opened).days
    if age_days < 0:
        result["blockers"].append("Account opening date is after the supplied current date.")
        return result
    fee_applies = age_days < rule["days"]
    fee = rule["fee"] if fee_applies else Decimal("0")
    balance = amount(target.get("balance"))
    balance_ok = balance is not None and (balance >= fee if fee_applies else balance == 0)
    result.update({"account_age_days": age_days, "early_closure_fee": format(fee, ".2f"),
                   "fee_applies": fee_applies, "notice_days": rule["notice_days"]})
    add_check(result, "balance_satisfies_closure_rule", balance_ok,
              "Balance is unknown or does not satisfy the closure rule (fee balance if early; otherwise zero).")
    result["eligible"] = not result["blockers"]
    return result


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"eligible": False, "blockers": ["Invalid JSON input: " + str(exc)], "checks": {}}))
        return
    accounts = request.get("accounts")
    if not isinstance(accounts, list):
        print(json.dumps({"eligible": False, "blockers": ["accounts must be a list."], "checks": {}}))
        return
    operation = request.get("operation")
    today = as_date(request.get("now"))
    if operation == "personal_savings_opening":
        result = personal_savings(accounts, request.get("identity_verified"), today)
    elif operation == "business_opening":
        result = business_opening(accounts, request.get("identity_verified"))
    elif operation == "closure":
        result = closure(accounts, request.get("target_account_id"), today, request)
    else:
        result = {"eligible": False, "checks": {}, "blockers": ["Unsupported operation."]}
    print(json.dumps(result, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
