#!/usr/bin/env python3
"""Assess structured credit-card closure prerequisites.

Input JSON schema:
{
  "today": "YYYY-MM-DD",
  "identity_verified": true|false,
  "account": {
    "account_id": "string", "user_id": "string",
    "date_of_account_open": "YYYY-MM-DD",
    "current_balance": "0.00" | number
  },
  "disputes": [{"status": "closed|open|pending|under_review|..."}],
  "replacement_orders": [{"status": "delivered|cancelled|pending|shipped|..."}],
  "closure_reason_history": []  # optional; include only records already determined
}

Output JSON includes `valid`, `eligible`, `blocked`, `reasons`, and `next_step`.
This helper makes no external calls and treats missing/ambiguous prerequisite data as
blocking. `closure_reason_history` is reported as informational because determining
whether a record falls within the past year may require record timestamps and policy
interpretation outside this helper.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_ORDER_STATUSES = {"delivered", "cancelled"}
NONFINAL_DISPUTE_STATUSES = {"open", "pending", "under_review", "active"}
FINAL_DISPUTE_STATUSES = {"closed", "resolved", "withdrawn", "denied"}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a YYYY-MM-DD string")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        errors.append(f"{field} must be a valid YYYY-MM-DD date")
        return None


def status_of(record):
    return record.get("status", "").strip().lower() if isinstance(record, dict) and isinstance(record.get("status", ""), str) else ""


def main(data):
    errors, reasons = [], []
    if not isinstance(data, dict):
        return {"valid": False, "eligible": False, "blocked": True, "reasons": ["Input must be a JSON object"], "next_step": "supply_structured_case_data"}

    today = parse_date(data.get("today"), "today", errors)
    account = data.get("account")
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    for key in ("account_id", "user_id"):
        if not isinstance(account.get(key), str) or not account[key].strip():
            errors.append(f"account.{key} must be a nonempty string")
    opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open", errors)

    balance = None
    try:
        raw_balance = str(account.get("current_balance", "")).replace("$", "").replace(",", "").strip()
        balance = Decimal(raw_balance)
    except (InvalidOperation, ValueError):
        errors.append("account.current_balance must be numeric")

    disputes = data.get("disputes")
    orders = data.get("replacement_orders")
    if not isinstance(disputes, list):
        errors.append("disputes must be a list from the dispute-history check")
        disputes = []
    if not isinstance(orders, list):
        errors.append("replacement_orders must be a list from the replacement-order check")
        orders = []

    if errors:
        return {"valid": False, "eligible": False, "blocked": True, "reasons": errors, "next_step": "obtain_complete_current_check_results"}

    if data.get("identity_verified") is not True:
        reasons.append("Identity has not been verified and logged")
    if opened > today:
        reasons.append("Account opening date is in the future")
    elif (today - opened).days < 60:
        reasons.append("Account has been open fewer than 60 days")
    if balance != Decimal("0"):
        reasons.append("Outstanding balance is not $0.00")

    ambiguous_disputes = []
    active_disputes = []
    for dispute in disputes:
        status = status_of(dispute)
        if status in NONFINAL_DISPUTE_STATUSES:
            active_disputes.append(status)
        elif status not in FINAL_DISPUTE_STATUSES:
            ambiguous_disputes.append(status or "missing status")
    if active_disputes:
        reasons.append("Active or pending dispute status: " + ", ".join(sorted(set(active_disputes))))
    if ambiguous_disputes:
        reasons.append("Ambiguous dispute status: " + ", ".join(sorted(set(ambiguous_disputes))))

    blocking_orders = []
    for order in orders:
        status = status_of(order)
        if status not in FINAL_ORDER_STATUSES:
            blocking_orders.append(status or "missing status")
    if blocking_orders:
        reasons.append("Pending or ambiguous replacement order status: " + ", ".join(sorted(set(blocking_orders))))

    eligible = not reasons
    history = data.get("closure_reason_history")
    prior_history_present = isinstance(history, list) and len(history) > 0
    return {
        "valid": True,
        "eligible": eligible,
        "blocked": not eligible,
        "reasons": reasons,
        "account_age_days": (today - opened).days,
        "prior_closure_history_present": prior_history_present,
        "next_step": "check_retention_history_and_handle_reason" if eligible else "resolve_blockers_before_retention_or_closure",
        "note": "Run a fresh replacement-order check immediately before the final closure action. Prior history must be evaluated for the past-year window."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "eligible": False, "blocked": True, "reasons": [f"Invalid JSON: {exc.msg}"], "next_step": "supply_valid_json"}))
