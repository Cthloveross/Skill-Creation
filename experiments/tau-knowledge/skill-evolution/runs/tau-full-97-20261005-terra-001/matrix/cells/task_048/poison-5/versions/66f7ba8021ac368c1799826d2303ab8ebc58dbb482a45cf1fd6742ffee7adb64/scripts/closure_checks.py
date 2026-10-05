#!/usr/bin/env python3
"""Evaluate structured credit-card closure eligibility from JSON on stdin.

This helper does no banking-tool calls. It is intentionally conservative: absent or
ambiguous data is reported as unknown and cannot make an account eligible.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "cancelled", "canceled"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S %Z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def normalized_status(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    return text or None


def parse_balance(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def add_one_year(value):
    try:
        return value.replace(year=value.year + 1)
    except ValueError:  # February 29
        return value.replace(year=value.year + 1, month=2, day=28)


def result(state, detail):
    return {"state": state, "detail": detail}


def evaluate(data):
    as_of = parse_date(data.get("as_of"))
    account = data.get("account") if isinstance(data.get("account"), dict) else None
    checks = {}

    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        checks["disputes"] = result("unknown", "Dispute list was not supplied as an array.")
    else:
        statuses = [normalized_status(item.get("status")) for item in disputes if isinstance(item, dict)]
        if len(statuses) != len(disputes) or any(status is None for status in statuses):
            checks["disputes"] = result("unknown", "At least one dispute lacks a usable status.")
        elif all(status in FINAL_DISPUTE_STATUSES for status in statuses):
            checks["disputes"] = result("pass", "No active or pending disputes were represented.")
        else:
            checks["disputes"] = result("fail", "At least one dispute is not clearly final.")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        checks["replacement_orders"] = result("unknown", "Replacement-order list was not supplied as an array.")
    else:
        statuses = [normalized_status(item.get("status")) for item in orders if isinstance(item, dict)]
        if len(statuses) != len(orders) or any(status is None for status in statuses):
            checks["replacement_orders"] = result("unknown", "At least one replacement order lacks a usable status.")
        elif all(status in FINAL_REPLACEMENT_STATUSES for status in statuses):
            checks["replacement_orders"] = result("pass", "No non-final replacement orders were represented.")
        else:
            checks["replacement_orders"] = result("fail", "At least one replacement order is not delivered or cancelled.")

    balance = parse_balance(account.get("current_balance")) if account else None
    if balance is None:
        checks["balance"] = result("unknown", "Current balance is absent or cannot be parsed.")
    elif balance == Decimal("0"):
        checks["balance"] = result("pass", "Current balance is exactly zero.")
    else:
        checks["balance"] = result("fail", "Current balance is not zero.")

    opened = parse_date(account.get("date_of_account_open")) if account else None
    age_days = None
    if as_of is None or opened is None:
        checks["account_age"] = result("unknown", "Current date or account-open date is absent or invalid.")
    else:
        age_days = (as_of - opened).days
        if age_days >= 60:
            checks["account_age"] = result("pass", "Account is open at least 60 days.")
        else:
            checks["account_age"] = result("fail", "Account is open fewer than 60 days.")

    eligible = all(item["state"] == "pass" for item in checks.values())
    return {
        "checks": checks,
        "account_age_days": age_days,
        "closure_eligible": eligible,
        "annual_fee_waiver_expiration_date": add_one_year(as_of).strftime("%m/%d/%Y") if as_of else None,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON value must be an object.")
        print(json.dumps(evaluate(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
