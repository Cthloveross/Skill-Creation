#!/usr/bin/env python3
"""Conservatively evaluate structured credit-card closure prerequisites.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
has no banking side effects and deliberately marks malformed or unfamiliar live
states for manual review rather than clearing them.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value):
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("balance must be numeric")


def statuses(records, label):
    if not isinstance(records, list):
        return None, [f"{label}_result_missing_or_malformed"]
    values = []
    problems = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("status"), str):
            problems.append(f"{label}_record_{index}_status_missing")
            continue
        values.append(record["status"].strip().lower())
    return values, problems


def main(payload):
    blockers = []
    details = {}

    try:
        today = parse_date(payload.get("current_date"))
        opened = parse_date(payload.get("account_open_date"))
        age_days = (today - opened).days
        details["account_age_days"] = age_days
        if age_days < 60:
            blockers.append("account_younger_than_60_days")
        if age_days < 0:
            blockers.append("account_open_date_is_in_the_future")
    except ValueError as exc:
        blockers.append("account_age_unverifiable")
        details["account_age_error"] = str(exc)

    try:
        balance = parse_money(payload.get("balance"))
        details["balance"] = format(balance, "f")
        if balance != Decimal("0"):
            blockers.append("outstanding_balance_not_zero")
    except ValueError as exc:
        blockers.append("balance_unverifiable")
        details["balance_error"] = str(exc)

    dispute_statuses, dispute_problems = statuses(payload.get("disputes"), "dispute")
    blockers.extend(dispute_problems)
    if dispute_statuses is not None:
        details["dispute_statuses"] = dispute_statuses
        unresolved = [s for s in dispute_statuses if s not in FINAL_DISPUTE_STATUSES]
        if unresolved:
            blockers.append("active_pending_or_unresolved_dispute")

    replacement_statuses, replacement_problems = statuses(
        payload.get("replacement_orders"), "replacement_order"
    )
    blockers.extend(replacement_problems)
    if replacement_statuses is not None:
        details["replacement_order_statuses"] = replacement_statuses
        nonfinal = [s for s in replacement_statuses if s not in FINAL_REPLACEMENT_STATUSES]
        if nonfinal:
            blockers.append("pending_or_unresolved_replacement_order")

    # Keep output stable and avoid duplicate explanations for one condition.
    blockers = list(dict.fromkeys(blockers))
    return {"eligible": not blockers, "blockers": blockers, "details": details}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible": False, "blockers": ["invalid_helper_input"], "details": {"error": str(exc)}}))
        sys.exit(2)
