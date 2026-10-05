#!/usr/bin/env python3
"""Read-only preflight assessment for combined banking-account requests.

Input: one JSON object on stdin, documented in SKILL.md.
Output: JSON object with errors, business_checking, personal_savings, and closures.
This program makes no tool calls and executes no banking action.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def value(record, *keys):
    for key in keys:
        if key in record:
            return record[key]
    return None


def account_id(record):
    return value(record, "account_id", "id")


def account_class(record):
    return value(record, "account_class", "level")


def amount(raw):
    if raw is None:
        return None
    try:
        return Decimal(str(raw).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def date(raw):
    if raw is None or str(raw).strip() == "":
        return None
    text = str(raw).strip()
    for fmt in (None, "%m/%d/%Y", "%Y-%m-%d"):
        try:
            if fmt is None:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def status(record):
    return str(record.get("status", "")).upper()


def role(record, roles):
    key = account_id(record)
    if key is not None and str(key) in roles:
        return roles[str(key)]
    return record.get("account_role") or record.get("role")


def pending(raw):
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, list):
        return any(isinstance(item, dict) and str(item.get("status", "")).lower() == "pending"
                   for item in raw)
    return None


def check(name, passed, detail):
    return {"name": name, "passed": passed, "detail": detail}


def closure_terms(kind, klass):
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
    return (savings if kind == "savings" else checking).get(klass)


def review_closure(record, kind, now, pending_value):
    blockers = []
    if status(record) != "OPEN":
        blockers.append("Account status must be OPEN.")
    is_pending = pending(pending_value)
    if is_pending is None:
        blockers.append("Pending transaction status must be retrieved.")
    elif is_pending:
        blockers.append("Pending transactions must clear.")

    terms = closure_terms(kind, account_class(record))
    opened = date(record.get("date_opened"))
    current = amount(value(record, "balance", "current_holdings"))
    result = {"account_id": str(account_id(record)), "kind": kind,
              "account_class": account_class(record), "blockers": blockers}
    if terms is None:
        blockers.append("Closure terms for this account class are unavailable.")
    elif now is None or opened is None:
        blockers.append("Current and opening dates are required for closure terms.")
    elif current is None:
        blockers.append("Current balance is required.")
    else:
        window, fee, notice_days, manager = terms
        age = max(0, (now - opened).days)
        fee_applies = age < window
        result.update({"age_days": age, "early_fee": str(fee if fee_applies else Decimal("0")),
                       "notice_days": notice_days, "manager_approval_required": manager})
        if fee_applies and current < fee:
            blockers.append("Balance is below the applicable early-closure fee.")
        if not fee_applies and current != 0:
            blockers.append("Balance must be zero because no early-closure fee applies.")
    result["eligible"] = not blockers
    return result


def assess(payload):
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not all(isinstance(item, dict) for item in accounts):
        return {"errors": ["accounts must be a list of objects."], "business_checking": None,
                "personal_savings": None, "closures": []}
    roles = payload.get("account_roles", {})
    pending_map = payload.get("pending_by_account", {})
    if not isinstance(roles, dict) or not isinstance(pending_map, dict):
        return {"errors": ["account_roles and pending_by_account must be objects."],
                "business_checking": None, "personal_savings": None, "closures": []}

    errors = []
    now = date(payload.get("now"))
    if payload.get("now") is not None and now is None:
        errors.append("now must be an ISO or MM/DD/YYYY date.")
    checkings = [item for item in accounts if str(item.get("account_type", "")).lower() == "checking"]
    personal_checkings = [item for item in checkings if role(item, roles) == "personal_checking"]
    business_checkings = [item for item in checkings if role(item, roles) == "business_checking"]

    business = None
    selected_business = payload.get("business_checking_class")
    if selected_business is not None:
        qualified_personal = [item for item in personal_checkings
                              if status(item) == "OPEN" and amount(value(item, "balance", "current_holdings")) is not None
                              and amount(value(item, "balance", "current_holdings")) >= Decimal("500")]
        checks = [
            check("verified", payload.get("user_verified") is True, "Customer must be verified."),
            check("personal_checking", bool(qualified_personal),
                  "An OPEN personal checking account with at least $500 is required."),
            check("business_limit", len(business_checkings) < 6,
                  "Customer must have fewer than six business checking accounts."),
            check("no_closed_accounts", all(status(item) != "CLOSED" for item in accounts),
                  "Customer must have no CLOSED account."),
            check("selected_class", isinstance(selected_business, str) and bool(selected_business.strip()),
                  "An exact business checking class is required."),
        ]
        business = {"checks": checks, "eligible": all(item["passed"] for item in checks)}

    savings = None
    selected_savings = payload.get("personal_savings_class")
    if selected_savings is not None:
        personal_savings = [item for item in accounts if role(item, roles) == "personal_savings"]
        tenure = any(status(item) in {"OPEN", "ACTIVE"} and now is not None and date(item.get("date_opened"))
                     and (now - date(item.get("date_opened"))).days >= 14 for item in personal_checkings)
        standing = all(amount(value(item, "balance", "current_holdings")) is not None
                       and amount(value(item, "balance", "current_holdings")) >= 0
                       and status(item) != "COLLECTIONS" for item in accounts)
        checks = [
            check("verified", payload.get("user_verified") is True, "Customer must be verified."),
            check("checking_tenure", tenure, "An active personal checking account held 14 days is required."),
            check("savings_limit", len(personal_savings) < 5, "Customer must hold fewer than five personal savings accounts."),
            check("good_standing", standing, "No account may be in collections or have a negative balance."),
            check("exact_class", isinstance(selected_savings, str) and selected_savings.strip().endswith("Account"),
                  "Savings class must end with 'Account'."),
        ]
        savings = {"checks": checks, "eligible": all(item["passed"] for item in checks)}

    closures = []
    by_id = {str(account_id(item)): item for item in accounts if account_id(item) is not None}
    for field, kind in (("close_savings_id", "savings"), ("close_checking_id", "checking")):
        target = payload.get(field)
        if target is None:
            continue
        record = by_id.get(str(target))
        if record is None:
            closures.append({"account_id": str(target), "kind": kind, "eligible": False,
                             "blockers": ["Requested account was not found."]})
        else:
            closures.append(review_closure(record, kind, now, pending_map.get(str(target))))
    return {"errors": errors, "business_checking": business, "personal_savings": savings, "closures": closures}


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(assess(source), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": ["Invalid helper input: " + str(exc)], "business_checking": None,
                          "personal_savings": None, "closures": []}, sort_keys=True))
