#!/usr/bin/env python3
"""Assess account-opening eligibility and checking closure preconditions.

Input JSON schema:
{
  "now": "YYYY-MM-DD ..." | "YYYY-MM-DD",
  "identity_verified": true|false,
  "customer_age": integer|null,
  "checking_closed_for_cause_last_6_months": true|false|null,
  "accounts": [{
    "account_id": "string",
    "account_type": "checking"|"savings"|..., "account_class": "string",
    "status": "OPEN"|"ACTIVE"|...,
    "balance": number|string|null, "date_opened": "YYYY-MM-DD..."|null,
    "pending_transactions": true|false|null,
    "in_collections": true|false|null
  }]
}

Output JSON contains pass/fail/unknown checks. The script is advisory; a bank
executor must still obtain authoritative pending/collections information and
customer authorization before performing any action.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def status(value):
    return str(value or "").strip().upper()


def finding(value, detail):
    return {"result": value, "detail": detail}


def all_known_false(values):
    return bool(values) and all(v is False for v in values)


def closure_rule(account, today):
    cls = account.get("account_class")
    rules = {
        "Light Blue Account": (15, 30, 0),
        "Light Green Account": (15, 30, 0),
        "Green Fee-Free Account": (15, 30, 0),
        "Blue Account": (25, 60, 3),
        "Green Account (checking)": (25, 60, 3),
        "Evergreen Account": (50, 90, 7),
        "Bluest Account": (100, 180, 14),
    }
    if cls not in rules:
        return {"account_id": account.get("account_id"), "eligible": False,
                "blockers": ["closure tier is not modeled; determine applicable fee and notice manually"]}
    fee, window, notice = rules[cls]
    blockers = []
    if status(account.get("status")) != "OPEN":
        blockers.append("status must be OPEN")
    pending = account.get("pending_transactions")
    if pending is not False:
        blockers.append("pending transaction status must be confirmed false")
    opened = parse_date(account.get("date_opened"))
    if not today or not opened:
        blockers.append("opening date/current date is required to determine early-closure fee")
        early = None
    else:
        early = (today - opened).days < window
    balance = money(account.get("balance"))
    if balance is None:
        blockers.append("exact current balance is required")
    elif early is True and balance < Decimal(fee):
        blockers.append("balance must cover the applicable early-closure fee of $%s" % fee)
    elif early is False and balance != Decimal("0"):
        blockers.append("balance must be exactly $0 when no early-closure fee applies")
    return {
        "account_id": account.get("account_id"), "account_class": cls,
        "early_closure": early, "early_fee_usd": fee if early else 0,
        "notice_days": notice, "eligible": not blockers, "blockers": blockers,
    }


def main(data):
    accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
    today = parse_date(data.get("now"))
    checking = [a for a in accounts if str(a.get("account_type", "")).lower() == "checking"]
    savings = [a for a in accounts if str(a.get("account_type", "")).lower() == "savings"]
    active_seasoned = []
    for a in checking:
        opened = parse_date(a.get("date_opened"))
        if status(a.get("status")) in ("ACTIVE", "OPEN") and today and opened and (today - opened).days >= 14:
            active_seasoned.append(a.get("account_id"))

    balances = [money(a.get("balance")) for a in accounts]
    negative_known = any(x is not None and x < 0 for x in balances)
    unknown_balance = any(x is None for x in balances)
    collections = [a.get("in_collections") for a in accounts]
    any_collections = any(x is True for x in collections)
    unknown_collections = any(x is None for x in collections)

    identity = data.get("identity_verified")
    age = data.get("customer_age")
    cause = data.get("checking_closed_for_cause_last_6_months")
    checking_checks = [
        finding("pass" if identity is True else "unknown" if identity is None else "fail", "identity verification must be logged"),
        finding("pass" if isinstance(age, int) and age >= 18 else "unknown" if age is None else "fail", "customer must be at least 18"),
        finding("pass" if len(checking) < 4 else "fail", "existing personal checking count is %d; must be fewer than 4 before opening" % len(checking)),
        finding("pass" if cause is False else "unknown" if cause is None else "fail", "no checking closure for cause in prior six months"),
    ]
    savings_checks = [
        finding("pass" if identity is True else "unknown" if identity is None else "fail", "identity verification must be logged"),
        finding("pass" if active_seasoned else "fail" if today else "unknown", "requires an ACTIVE/OPEN checking account held at least 14 days"),
        finding("pass" if len(savings) < 5 else "fail", "existing personal savings count is %d; must be fewer than 5" % len(savings)),
        finding("fail" if negative_known else "unknown" if unknown_balance else "pass", "no account may have a negative balance"),
        finding("fail" if any_collections else "unknown" if unknown_collections else "pass", "no account may be in collections"),
    ]
    result = {
        "checking_opening": {"eligible": all(x["result"] == "pass" for x in checking_checks), "checks": checking_checks},
        "savings_opening": {"eligible": all(x["result"] == "pass" for x in savings_checks), "qualifying_checking_account_ids": active_seasoned, "checks": savings_checks},
        "checking_closures": [closure_rule(a, today) for a in checking],
        "notes": ["An exact customer-confirmed official account class is still required to open either account.", "Closure assessment does not authorize a closure and cannot replace a live pending-transaction check."],
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), default=str, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
