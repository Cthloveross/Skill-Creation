#!/usr/bin/env python3
"""Evaluate supplied account-transition checklist facts without taking bank actions.

Reads a JSON object from stdin and emits JSON. Unknown/missing facts remain unknown.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def value(data, key):
    return data[key] if key in data and data[key] is not None else None


def checklist(required):
    blockers = []
    unknown = []
    for label, actual, predicate, failure in required:
        if actual is None:
            unknown.append(label)
        elif not predicate(actual):
            blockers.append(failure)
    return {"eligible": not blockers and not unknown, "blockers": blockers, "unknown": unknown}


def decimal_or_none(item):
    if item is None:
        return None
    try:
        return Decimal(str(item))
    except (InvalidOperation, ValueError):
        return None


def closure_rule(account_class, age_days):
    rules = {
        "Light Blue Account": (30, Decimal("15"), 0),
        "Light Green Account": (30, Decimal("15"), 0),
        "Green Fee-Free Account": (30, Decimal("15"), 0),
        "Blue Account": (60, Decimal("25"), 3),
        "Green Account (checking)": (60, Decimal("25"), 3),
        "Evergreen Account": (90, Decimal("50"), 7),
        "Bluest Account": (180, Decimal("100"), 14),
    }
    if account_class not in rules or age_days is None:
        return None
    window, fee, notice = rules[account_class]
    return {"early_fee": fee if age_days < window else Decimal("0"), "notice_days": notice}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    checking = checklist([
        ("verified", value(data, "verified"), lambda x: x is True, "customer is not verified"),
        ("age_years", value(data, "age_years"), lambda x: x >= 18, "customer is under 18"),
        ("checking_count", value(data, "checking_count"), lambda x: x <= 4, "checking account limit reached"),
        ("recent_checking_closed_for_cause", value(data, "recent_checking_closed_for_cause"), lambda x: x is False, "recent checking closure for cause"),
    ])
    savings = checklist([
        ("verified", value(data, "verified"), lambda x: x is True, "customer is not verified"),
        ("checking_open", value(data, "checking_open"), lambda x: x is True, "no active checking account"),
        ("checking_age_days", value(data, "checking_age_days"), lambda x: x >= 14, "checking tenure is below 14 days"),
        ("savings_count", value(data, "savings_count"), lambda x: x < 5, "personal savings account limit reached"),
        ("has_collections", value(data, "has_collections"), lambda x: x is False, "accounts in collections"),
        ("has_negative_balance", value(data, "has_negative_balance"), lambda x: x is False, "negative account balance exists"),
    ])

    raw_closure = value(data, "closure")
    if raw_closure is None:
        closure = {"eligible": False, "blockers": [], "unknown": ["closure"]}
    elif not isinstance(raw_closure, dict):
        closure = {"eligible": False, "blockers": ["closure must be an object"], "unknown": []}
    else:
        age_days = value(raw_closure, "age_days")
        account_class = value(raw_closure, "account_class")
        rule = closure_rule(account_class, age_days)
        balance = decimal_or_none(value(raw_closure, "balance"))
        closure = checklist([
            ("status", value(raw_closure, "status"), lambda x: x == "OPEN", "account is not OPEN"),
            ("pending_transactions", value(raw_closure, "pending_transactions"), lambda x: x is False, "pending transactions exist"),
            ("debit_cards_closed", value(raw_closure, "debit_cards_closed"), lambda x: x is True, "linked debit cards must be closed first"),
        ])
        if rule is None:
            closure["unknown"].append("recognized account class and closure age")
        elif balance is None:
            closure["unknown"].append("closure balance")
        else:
            fee = rule["early_fee"]
            if fee > 0 and balance < fee:
                closure["blockers"].append("balance is below applicable early closure fee")
            if fee == 0 and balance != 0:
                closure["blockers"].append("balance must be zero when no early closure fee applies")
            closure["applicable_early_fee"] = format(fee, ".2f")
            closure["notice_days"] = rule["notice_days"]
        closure["eligible"] = not closure["blockers"] and not closure["unknown"]

    print(json.dumps({
        "checking_opening": checking,
        "savings_opening": savings,
        "closure": closure,
        "disclaimer": "Checklist output is not authorization and does not perform any banking action."
    }, sort_keys=True))


if __name__ == "__main__":
    main()
