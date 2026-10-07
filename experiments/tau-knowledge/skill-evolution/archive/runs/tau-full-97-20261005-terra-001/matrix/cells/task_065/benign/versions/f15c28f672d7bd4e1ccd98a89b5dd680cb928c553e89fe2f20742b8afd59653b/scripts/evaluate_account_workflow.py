#!/usr/bin/env python3
"""Evaluate documented account-opening and checking-closure prerequisites.

Input JSON schema is documented in SKILL.md. The program does not call tools, make
recommendations, or execute banking actions. Unknown values are represented by null
and make the relevant readiness result false.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    return None


def decimal_value(value):
    if value is None:
        return None
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def check(name, passed, detail):
    return {"requirement": name, "pass": passed, "detail": detail}


def ready(checks):
    return bool(checks) and all(item["pass"] is True for item in checks)


def is_open_or_active(account):
    return str(account.get("status", "")).upper() in {"OPEN", "ACTIVE"}


def main(data):
    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be a list")
    requested = data.get("requested") or {}
    as_of = parse_date(data.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be YYYY-MM-DD or MM/DD/YYYY")

    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    verified = data.get("identity_verified")
    age = data.get("age")
    close_for_cause = data.get("checking_closed_for_cause_last_6_months")

    checking_checks = [
        check("identity is verified", verified if isinstance(verified, bool) else None,
              "Verification must be logged after matching two required identity fields."),
        check("customer is at least 18", (int(age) >= 18) if age is not None else None,
              "Age is calculated from a verified date of birth."),
        check("existing personal checking count does not exceed 4", len(checking) <= 4,
              "Current checking count is %d." % len(checking)),
        check("no checking closure for cause in prior 6 months",
              (not close_for_cause) if isinstance(close_for_cause, bool) else None,
              "This must come from an authorized account-history source."),
    ]

    active_checking = []
    qualifying_tenure = []
    for account in checking:
        if is_open_or_active(account):
            active_checking.append(account)
            opened = parse_date(account.get("date_opened"))
            if opened is not None and (as_of - opened).days >= 14:
                qualifying_tenure.append(account)

    collections_values = [a.get("in_collections") for a in accounts]
    collections_known = all(isinstance(v, bool) for v in collections_values)
    has_collections = any(v is True for v in collections_values) if collections_known else None
    balances = [decimal_value(a.get("balance")) for a in accounts]
    balances_known = all(v is not None for v in balances)
    has_negative = any(v < 0 for v in balances) if balances_known else None

    savings_checks = [
        check("identity is verified", verified if isinstance(verified, bool) else None,
              "Verification must be logged after matching two required identity fields."),
        check("active or open Rho-Bank checking exists", bool(active_checking),
              "Found %d active/open checking account(s)." % len(active_checking)),
        check("an active/open checking account has at least 14 days tenure", bool(qualifying_tenure),
              "Found %d qualifying checking account(s)." % len(qualifying_tenure)),
        check("fewer than 5 personal savings accounts", len(savings) < 5,
              "Current savings count is %d." % len(savings)),
        check("no accounts are in collections", (not has_collections) if collections_known else None,
              "Collections status must be known for every account."),
        check("no account has a negative balance", (not has_negative) if balances_known else None,
              "Balances must be known for every account."),
    ]

    closure = {"requested": bool(requested.get("close_account_id")), "checks": [], "ready": False}
    close_id = requested.get("close_account_id")
    if close_id:
        account = next((a for a in accounts if str(a.get("account_id")) == str(close_id)), None)
        if account is None:
            closure["checks"] = [check("requested account exists", False, "No supplied account has this account_id.")]
        else:
            klass = str(account.get("account_class", ""))
            entry_classes = {"Light Blue Account", "Light Green Account", "Green Fee-Free Account"}
            opened = parse_date(account.get("date_opened"))
            age_days = (as_of - opened).days if opened else None
            early_fee = Decimal("15") if klass in entry_classes and age_days is not None and age_days < 30 else Decimal("0")
            balance = decimal_value(account.get("balance"))
            pending = account.get("pending_transactions")
            if early_fee > 0:
                balance_pass = (balance >= early_fee) if balance is not None else None
                balance_detail = "Early closure fee is $15; balance must be at least $15."
            else:
                balance_pass = (balance == 0) if balance is not None else None
                balance_detail = "No early fee applies; balance must be exactly $0."
            closure["account_class"] = klass
            closure["account_age_days"] = age_days
            closure["early_closure_fee"] = str(early_fee)
            closure["checks"] = [
                check("account status is OPEN", str(account.get("status", "")).upper() == "OPEN",
                      "Closure policy requires status OPEN."),
                check("no pending transactions", (not pending) if isinstance(pending, bool) else None,
                      "Inspect transaction history; missing pending status is not a pass."),
                check("balance satisfies closure rule", balance_pass, balance_detail),
            ]
        closure["ready"] = ready(closure["checks"])

    output = {
        "checking_opening": {"checks": checking_checks, "ready": ready(checking_checks)},
        "savings_opening": {"checks": savings_checks, "ready": ready(savings_checks)},
        "closure": closure,
        "counts": {"checking": len(checking), "savings": len(savings)},
        "selected_classes": {
            "checking": requested.get("checking_class"),
            "savings": requested.get("savings_class"),
        },
        "note": "A ready result is only an eligibility assessment. Explicit customer authorization and successful tool results are still required."
    }
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
