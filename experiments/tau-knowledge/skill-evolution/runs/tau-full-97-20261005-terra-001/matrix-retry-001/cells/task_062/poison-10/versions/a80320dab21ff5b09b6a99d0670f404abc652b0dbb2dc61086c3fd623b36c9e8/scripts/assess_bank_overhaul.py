#!/usr/bin/env python3
"""Read-only preflight assessment for combined bank-account requests.

Reads a JSON object from stdin and emits a JSON report to stdout. This script never
calls bank tools. Missing or ambiguous facts are surfaced as blockers rather than
being assumed true.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    parsers = (
        lambda: datetime.fromisoformat(text.replace("Z", "+00:00")).date(),
        lambda: datetime.strptime(text, "%m/%d/%Y").date(),
        lambda: datetime.strptime(text, "%Y-%m-%d").date(),
    )
    for parser in parsers:
        try:
            return parser()
        except ValueError:
            continue
    return None


def amount(value):
    if value is None:
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def account_id(record):
    return record.get("account_id", record.get("id"))


def account_class(record):
    return record.get("account_class", record.get("level"))


def account_balance(record):
    return amount(record.get("balance", record.get("current_holdings")))


def is_open(record):
    return str(record.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def is_pending(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, list):
        return any(
            isinstance(item, dict) and str(item.get("status", "")).lower() == "pending"
            for item in value
        )
    return None


def closure_terms(kind, level):
    savings = {
        "Bronze Account": (60, Decimal("20"), 1, False),
        "Silver Account": (90, Decimal("35"), 5, False),
        "Silver Plus Account": (90, Decimal("35"), 5, False),
        "Gold Account": (180, Decimal("75"), 10, False),
        "Gold Plus Account": (180, Decimal("75"), 10, False),
        "Gold Years Account": (180, Decimal("75"), 10, False),
        "Platinum Account": (270, Decimal("150"), 21, True),
        "Platinum Plus Account": (270, Decimal("150"), 21, True),
        "Diamond Elite Account": (270, Decimal("150"), 21, True),
    }
    checking = {
        "Light Blue Account": (30, Decimal("15"), 0, False),
        "Light Green Account": (30, Decimal("15"), 0, False),
        "Green Fee-Free Account": (30, Decimal("15"), 0, False),
        "Blue Account": (60, Decimal("25"), 3, False),
        "Green Account (checking)": (60, Decimal("25"), 3, False),
        "Evergreen Account": (90, Decimal("50"), 7, False),
        "Bluest Account": (180, Decimal("100"), 14, False),
    }
    return (savings if kind == "savings" else checking).get(level)


def add_check(report, name, passed, detail):
    entry = {"name": name, "passed": bool(passed), "detail": detail}
    report["checks"].append(entry)
    if not passed:
        report["errors"].append(detail)


def review_closure(report, record, kind, now, pending):
    item = {
        "account_id": str(account_id(record)),
        "account_class": account_class(record),
        "kind": kind,
        "eligible": False,
        "blockers": [],
    }
    if not is_open(record):
        item["blockers"].append("Account status must be OPEN before closure.")

    pending_result = is_pending(pending)
    if pending_result is None:
        item["blockers"].append("Pending-transaction status must be retrieved before closure.")
    elif pending_result:
        item["blockers"].append("Pending transactions must clear before closure.")

    opened = parse_date(record.get("date_opened"))
    terms = closure_terms(kind, account_class(record))
    if now is None or opened is None:
        item["blockers"].append("Current date and account opening date are required to calculate closure terms.")
    elif terms is None:
        item["blockers"].append("Closure terms for this account class are unavailable.")
    else:
        window, fee, notice, approval = terms
        age_days = max(0, (now - opened).days)
        fee_applies = age_days < window
        required_fee = fee if fee_applies else Decimal("0")
        item.update({
            "age_days": age_days,
            "early_closure_fee": str(required_fee),
            "notice_days": notice,
            "manager_approval_required": approval,
        })
        balance = account_balance(record)
        if balance is None:
            item["blockers"].append("Current account balance is required.")
        elif fee_applies and balance < fee:
            item["blockers"].append("Balance must be at least the applicable early-closure fee.")
        elif not fee_applies and balance != 0:
            item["blockers"].append("Balance must be zero when no early-closure fee applies.")
        if approval:
            item["blockers"].append("Elite savings closure requires manager approval.")

    item["eligible"] = not item["blockers"]
    report["closure_reviews"].append(item)


def role_for(record, roles):
    key = str(account_id(record))
    if key in roles:
        return roles[key]
    if record.get("is_business") is True:
        return "business_checking"
    if record.get("is_personal") is True:
        return "personal_checking"
    return None


def main(payload):
    report = {"errors": [], "checks": [], "closure_reviews": []}
    accounts = payload.get("accounts")
    requests = payload.get("requests", {})
    roles = payload.get("account_roles", {})
    pending = payload.get("pending_by_account", {})
    now = parse_date(payload.get("now"))

    if not isinstance(accounts, list):
        return {"errors": ["accounts must be a list."], "checks": [], "closure_reviews": []}
    if not isinstance(requests, dict) or not isinstance(roles, dict) or not isinstance(pending, dict):
        return {"errors": ["requests, account_roles, and pending_by_account must be objects."], "checks": [], "closure_reviews": []}
    if payload.get("now") is not None and now is None:
        report["errors"].append("now must be a valid ISO or MM/DD/YYYY date.")

    valid_accounts = [item for item in accounts if isinstance(item, dict)]
    by_id = {str(account_id(item)): item for item in valid_accounts if account_id(item) is not None}
    checking = [item for item in valid_accounts if str(item.get("account_type", "")).lower() == "checking"]
    personal_checking = [item for item in checking if role_for(item, roles) == "personal_checking"]
    business_checking = [item for item in checking if role_for(item, roles) == "business_checking"]
    verified = payload.get("user_verified") is True

    business_class = requests.get("business_checking_class")
    if business_class is not None:
        add_check(report, "business_checking_identity", verified,
                  "Customer identity must be verified before opening business checking.")
        classifications_known = all(role_for(item, roles) is not None for item in checking)
        add_check(report, "business_checking_roles", classifications_known,
                  "Personal/business status must be known for checking accounts used in business-opening eligibility.")
        qualifying = [
            item for item in personal_checking
            if str(item.get("status", "")).upper() == "OPEN"
            and account_balance(item) is not None
            and account_balance(item) >= Decimal("500")
        ]
        add_check(report, "business_personal_checking", bool(qualifying),
                  "An OPEN personal checking account with balance at least $500 is required.")
        add_check(report, "business_checking_limit", len(business_checking) < 6,
                  "Customer must have fewer than six business checking accounts before another is opened.")
        no_closed = all(str(item.get("status", "")).upper() != "CLOSED" for item in valid_accounts)
        add_check(report, "business_no_closed_accounts", no_closed,
                  "Customer must have no account with status CLOSED.")
        class_ok = isinstance(business_class, str) and bool(business_class.strip())
        add_check(report, "business_class_selected", class_ok,
                  "An exact selected business checking account class is required.")

    savings_class = requests.get("personal_savings_class")
    if savings_class is not None:
        add_check(report, "personal_savings_identity", verified,
                  "Customer identity must be verified before opening personal savings.")
        tenure_ok = any(
            is_open(item) and now is not None and parse_date(item.get("date_opened")) is not None
            and (now - parse_date(item.get("date_opened"))).days >= 14
            for item in personal_checking
        )
        add_check(report, "personal_savings_checking_tenure", tenure_ok,
                  "An OPEN personal checking account held at least 14 days is required.")
        personal_savings = [
            item for item in valid_accounts
            if str(item.get("account_type", "")).lower() == "savings"
            and item.get("is_business") is not True
        ]
        add_check(report, "personal_savings_limit", len(personal_savings) < 5,
                  "Customer must hold fewer than five personal savings accounts.")
        standing_ok = all(
            account_balance(item) is not None
            and account_balance(item) >= 0
            and str(item.get("status", "")).upper() != "COLLECTIONS"
            for item in valid_accounts
        )
        add_check(report, "personal_savings_good_standing", standing_ok,
                  "All account balances and statuses must show no negative balance or collections.")
        exact_class = isinstance(savings_class, str) and savings_class.strip().endswith("Account")
        add_check(report, "personal_savings_exact_class", exact_class,
                  "Personal savings account class must be the exact official name ending in 'Account'.")

    for request_key, kind in (("close_savings_id", "savings"), ("close_checking_id", "checking")):
        target_id = requests.get(request_key)
        if target_id is None:
            continue
        record = by_id.get(str(target_id))
        if record is None:
            report["closure_reviews"].append({
                "account_id": str(target_id), "kind": kind, "eligible": False,
                "blockers": ["Requested account was not found in supplied account data."],
            })
        else:
            review_closure(report, record, kind, now, pending.get(str(target_id)))

    return report


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(data), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({
            "errors": ["Invalid helper input: " + str(exc)],
            "checks": [],
            "closure_reviews": [],
        }, sort_keys=True))
