#!/usr/bin/env python3
"""Read-only preflight assessment for combined banking-account requests.

Input: one JSON object on stdin, as documented in SKILL.md.
Output: one JSON object containing errors, checks, and closure_reviews.
This script never calls tools or executes banking actions.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if value is None or value == "":
        return None
    text = str(value).strip()
    for parser in (
        lambda: datetime.fromisoformat(text.replace("Z", "+00:00")).date(),
        lambda: datetime.strptime(text, "%m/%d/%Y").date(),
        lambda: datetime.strptime(text, "%Y-%m-%d").date(),
    ):
        try:
            return parser()
        except ValueError:
            pass
    return None


def parse_amount(value):
    if value is None:
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def identifier(record):
    return record.get("account_id", record.get("id"))


def account_class(record):
    return record.get("account_class", record.get("level"))


def balance(record):
    return parse_amount(record.get("balance", record.get("current_holdings")))


def is_open(record):
    return str(record.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def pending_status(value):
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


def role_for(record, roles):
    key = str(identifier(record))
    if key in roles:
        return roles[key]
    if record.get("is_business") is True:
        account_type = str(record.get("account_type", "")).lower()
        return "business_checking" if account_type == "checking" else "business_savings"
    if record.get("is_personal") is True:
        account_type = str(record.get("account_type", "")).lower()
        return "personal_checking" if account_type == "checking" else "personal_savings"
    return None


def add_check(report, name, passed, detail):
    report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})
    if not passed:
        report["errors"].append(detail)


def review_closure(report, record, kind, now, pending, notice_ok, manager_ok):
    item = {
        "account_id": str(identifier(record)),
        "account_class": account_class(record),
        "kind": kind,
        "eligible": False,
        "blockers": [],
    }
    if str(record.get("status", "")).upper() != "OPEN":
        item["blockers"].append("Account status must be OPEN before closure.")

    pending = pending_status(pending)
    if pending is None:
        item["blockers"].append("Pending-transaction status must be retrieved before closure.")
    elif pending:
        item["blockers"].append("Pending transactions must clear before closure.")

    opened = parse_date(record.get("date_opened"))
    terms = closure_terms(kind, account_class(record))
    if now is None or opened is None:
        item["blockers"].append("Current date and account opening date are required to calculate closure terms.")
    elif terms is None:
        item["blockers"].append("Closure terms for this account class are unavailable.")
    else:
        window, fee, notice_days, needs_manager = terms
        age_days = max(0, (now - opened).days)
        fee_applies = age_days < window
        current_balance = balance(record)
        item.update({
            "age_days": age_days,
            "early_closure_fee": str(fee if fee_applies else Decimal("0")),
            "notice_days": notice_days,
            "manager_approval_required": needs_manager,
        })
        if current_balance is None:
            item["blockers"].append("Current account balance is required.")
        elif fee_applies and current_balance < fee:
            item["blockers"].append("Balance must be at least the applicable early-closure fee.")
        elif not fee_applies and current_balance != 0:
            item["blockers"].append("Balance must be zero when no early-closure fee applies.")
        if notice_days and notice_ok is not True:
            item["blockers"].append("Required closure notice is not documented as satisfied.")
        if needs_manager and manager_ok is not True:
            item["blockers"].append("Elite savings closure requires manager approval.")

    item["eligible"] = not item["blockers"]
    report["closure_reviews"].append(item)


def main(payload):
    report = {"errors": [], "checks": [], "closure_reviews": []}
    accounts = payload.get("accounts")
    requests = payload.get("requests", {})
    roles = payload.get("account_roles", {})
    pending = payload.get("pending_by_account", {})
    notices = payload.get("notice_satisfied_by_account", {})
    approvals = payload.get("manager_approved_by_account", {})
    now = parse_date(payload.get("now"))

    if not isinstance(accounts, list):
        return {"errors": ["accounts must be a list."], "checks": [], "closure_reviews": []}
    if not all(isinstance(value, dict) for value in (requests, roles, pending, notices, approvals)):
        return {"errors": ["requests and all account mappings must be JSON objects."], "checks": [], "closure_reviews": []}
    if payload.get("now") is not None and now is None:
        report["errors"].append("now must be an ISO or MM/DD/YYYY date.")

    valid = [record for record in accounts if isinstance(record, dict)]
    by_id = {str(identifier(record)): record for record in valid if identifier(record) is not None}
    checking = [record for record in valid if str(record.get("account_type", "")).lower() == "checking"]
    personal_checking = [record for record in checking if role_for(record, roles) == "personal_checking"]
    business_checking = [record for record in checking if role_for(record, roles) == "business_checking"]

    business_class = requests.get("business_checking_class")
    if business_class is not None:
        add_check(report, "business_identity", payload.get("user_verified") is True,
                  "Customer identity must be verified before opening business checking.")
        add_check(report, "business_role_classification", all(role_for(record, roles) for record in checking),
                  "Checking-account roles must be known to assess business-opening eligibility.")
        qualifying = [record for record in personal_checking if
                      str(record.get("status", "")).upper() == "OPEN" and
                      balance(record) is not None and balance(record) >= Decimal("500")]
        add_check(report, "business_personal_checking", bool(qualifying),
                  "An OPEN personal checking account with balance at least $500 is required.")
        add_check(report, "business_limit", len(business_checking) < 6,
                  "Customer must have fewer than six business checking accounts.")
        add_check(report, "business_no_closed", all(str(record.get("status", "")).upper() != "CLOSED" for record in valid),
                  "Customer must have no account with status CLOSED.")
        add_check(report, "business_selected_class", isinstance(business_class, str) and bool(business_class.strip()),
                  "An exact selected business checking class is required.")

    savings_class = requests.get("personal_savings_class")
    if savings_class is not None:
        personal_savings = [record for record in valid if role_for(record, roles) == "personal_savings"]
        tenure_ok = any(is_open(record) and now is not None and parse_date(record.get("date_opened")) is not None and
                        (now - parse_date(record.get("date_opened"))).days >= 14
                        for record in personal_checking)
        standing_ok = all(balance(record) is not None and balance(record) >= 0 and
                          str(record.get("status", "")).upper() != "COLLECTIONS" for record in valid)
        add_check(report, "savings_identity", payload.get("user_verified") is True,
                  "Customer identity must be verified before opening personal savings.")
        add_check(report, "savings_checking_tenure", tenure_ok,
                  "An OPEN personal checking account held at least 14 days is required.")
        add_check(report, "savings_limit", len(personal_savings) < 5,
                  "Customer must hold fewer than five personal savings accounts.")
        add_check(report, "savings_good_standing", standing_ok,
                  "No account may have a negative balance or collections status.")
        add_check(report, "savings_exact_class", isinstance(savings_class, str) and savings_class.strip().endswith("Account"),
                  "Personal savings class must be the exact official name ending in 'Account'.")

    for request_key, kind in (("close_savings_id", "savings"), ("close_checking_id", "checking")):
        target = requests.get(request_key)
        if target is None:
            continue
        record = by_id.get(str(target))
        if record is None:
            report["closure_reviews"].append({"account_id": str(target), "kind": kind, "eligible": False,
                                              "blockers": ["Requested account was not found in supplied account data."]})
        else:
            key = str(target)
            review_closure(report, record, kind, now, pending.get(key), notices.get(key), approvals.get(key))
    return report


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"errors": ["Invalid helper input: " + str(exc)], "checks": [], "closure_reviews": []}, sort_keys=True))
