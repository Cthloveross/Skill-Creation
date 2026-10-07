#!/usr/bin/env python3
"""Assess documented credit-card closure prerequisites from supplied facts.

Reads one JSON object from stdin and emits one JSON object to stdout.  This helper
is deliberately side-effect-free and cannot make banking calls.
"""

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
RESOLVED_DISPUTE_STATUSES = {"closed", "resolved", "withdrawn", "denied"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    # Timestamps supplied by the runtime normally begin with YYYY-MM-DD.
    candidates = ("%Y-%m-%d", "%m/%d/%Y")
    for fmt in candidates:
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass
    # Permit an unambiguous date embedded in a longer timestamp.
    match = re.search(r"(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", value)
    if match:
        return parse_date(match.group(1))
    return None


def parse_money(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if not isinstance(value, str):
        return None
    normalized = value.strip().replace(",", "").replace("$", "")
    # Reject text such as an account label instead of silently accepting it.
    if not re.fullmatch(r"[-+]?\d+(?:\.\d{1,2})?", normalized):
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def result(state, detail):
    return {"state": state, "detail": detail}


def assess(payload):
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    now = parse_date(payload.get("current_time"))
    opened = parse_date(account.get("date_of_account_open"))
    balance = parse_money(account.get("current_balance"))

    checks = {}
    if balance is None:
        checks["zero_balance"] = result("review", "Balance is missing or not a recognized currency value.")
    elif balance == Decimal("0"):
        checks["zero_balance"] = result("pass", "Outstanding balance is zero.")
    else:
        checks["zero_balance"] = result("fail", "Outstanding balance is not zero.")

    if now is None or opened is None:
        checks["account_age"] = result("review", "Current date or account-open date is unavailable or invalid.")
    elif opened > now:
        checks["account_age"] = result("review", "Account-open date is in the future.")
    elif (now - opened).days >= 60:
        checks["account_age"] = result("pass", "Account is at least 60 days old.")
    else:
        checks["account_age"] = result("fail", "Account is younger than 60 days.")

    disputes = payload.get("disputes")
    if not isinstance(disputes, list):
        checks["pending_disputes"] = result("review", "Dispute records are missing or malformed.")
    else:
        unknown = False
        blocking = False
        for dispute in disputes:
            if not isinstance(dispute, dict) or not isinstance(dispute.get("status"), str):
                unknown = True
                continue
            status = dispute["status"].strip().lower()
            if status not in RESOLVED_DISPUTE_STATUSES:
                blocking = True
        if blocking:
            checks["pending_disputes"] = result("fail", "At least one supplied dispute is not clearly resolved.")
        elif unknown:
            checks["pending_disputes"] = result("review", "At least one supplied dispute has no usable status.")
        else:
            checks["pending_disputes"] = result("pass", "No supplied disputes are active or pending.")

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        checks["replacement_orders"] = result("review", "Replacement-order records are missing or malformed.")
    else:
        unknown = False
        blocking = False
        for order in orders:
            if not isinstance(order, dict) or not isinstance(order.get("status"), str):
                unknown = True
                continue
            if order["status"].strip().lower() not in FINAL_REPLACEMENT_STATUSES:
                blocking = True
        if blocking:
            checks["replacement_orders"] = result("fail", "At least one replacement order is not final.")
        elif unknown:
            checks["replacement_orders"] = result("review", "At least one replacement order has no usable status.")
        else:
            checks["replacement_orders"] = result("pass", "No pending replacement orders were supplied.")

    states = [item["state"] for item in checks.values()]
    decision = "blocked" if "fail" in states else "review_required" if "review" in states else "eligible"
    return {"decision": decision, "checks": checks}


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(assess(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"decision": "review_required", "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
