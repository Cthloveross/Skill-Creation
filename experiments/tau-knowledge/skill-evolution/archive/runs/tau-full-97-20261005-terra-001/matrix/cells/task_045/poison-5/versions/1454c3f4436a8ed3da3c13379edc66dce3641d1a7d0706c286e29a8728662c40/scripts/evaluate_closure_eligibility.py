#!/usr/bin/env python3
"""Evaluate factual account-closure eligibility supplied as JSON on stdin.

This helper performs no retrievals or account actions. It emits a single JSON object
on stdout and is deliberately conservative: missing or malformed required facts
produce an indeterminate result.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing balance")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        if cleaned:
            try:
                return Decimal(cleaned)
            except InvalidOperation:
                pass
    raise ValueError("balance must be a currency string or number")


def check_account_age(data):
    try:
        today = parse_date(data.get("current_date"))
        opened = parse_date(data.get("date_of_account_open"))
    except ValueError as exc:
        return "unknown", str(exc)
    age_days = (today - opened).days
    if age_days < 0:
        return "fail", "account opening date is in the future"
    if age_days < 60:
        return "fail", "account has been open fewer than 60 days"
    return "pass", None


def check_balance(data):
    try:
        balance = parse_money(data.get("current_balance"))
    except ValueError as exc:
        return "unknown", str(exc)
    if balance == Decimal("0"):
        return "pass", None
    return "fail", "outstanding balance is not $0.00"


def check_disputes(data):
    value = data.get("pending_disputes")
    if value is None:
        return "unknown", "pending-dispute status was not supplied"
    if not isinstance(value, bool):
        return "unknown", "pending_disputes must be boolean or null"
    return ("fail", "active or pending dispute exists") if value else ("pass", None)


def check_replacements(data):
    orders = data.get("replacement_orders")
    if orders is None:
        return "unknown", "replacement-order result was not supplied"
    if not isinstance(orders, list):
        return "unknown", "replacement_orders must be a list or null"
    nonfinal = []
    for index, order in enumerate(orders):
        status = order.get("status") if isinstance(order, dict) else None
        normalized = status.strip().lower() if isinstance(status, str) else ""
        if normalized not in FINAL_REPLACEMENT_STATUSES:
            nonfinal.append(index)
    if nonfinal:
        return "fail", "one or more replacement orders are not clearly delivered or cancelled"
    return "pass", None


def evaluate(data):
    checks = {
        "zero_balance": check_balance(data),
        "no_pending_disputes": check_disputes(data),
        "minimum_account_age": check_account_age(data),
        "no_pending_replacement_orders": check_replacements(data),
    }
    states = {name: result[0] for name, result in checks.items()}
    blockers = [reason for state, reason in checks.values() if state == "fail" and reason]
    unknowns = [reason for state, reason in checks.values() if state == "unknown" and reason]

    if blockers:
        eligibility = "not_eligible"
    elif unknowns:
        eligibility = "indeterminate"
    else:
        eligibility = "eligible"

    return {
        "eligibility": eligibility,
        "checks": states,
        "blocking_reasons": blockers,
        "unknown_reasons": unknowns,
        "can_begin_retention": eligibility == "eligible",
        "can_close_based_on_eligibility_only": eligibility == "eligible",
        "limitations": [
            "This result does not verify identity, confirm pending transactions, retrieve live data, or perform closure.",
            "Closure still requires logged identity verification, current authorized checks, customer confirmation, and the normal closure workflow."
        ]
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        result = evaluate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "eligibility": "indeterminate",
            "checks": {},
            "blocking_reasons": [],
            "unknown_reasons": [str(exc)],
            "can_begin_retention": False,
            "can_close_based_on_eligibility_only": False
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
