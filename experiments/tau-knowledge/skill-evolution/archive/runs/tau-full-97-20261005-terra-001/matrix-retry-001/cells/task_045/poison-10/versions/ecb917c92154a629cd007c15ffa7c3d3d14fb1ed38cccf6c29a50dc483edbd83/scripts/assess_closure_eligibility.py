#!/usr/bin/env python3
"""Conservative credit-card closure eligibility assessment.

Reads one JSON object from stdin and writes one JSON object to stdout. This
program is advisory: the executor must still obtain fresh tool results and
perform identity verification before a closure action.
"""

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "completed", "withdrawn", "cancelled"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("current_balance must be a number or currency string")
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if not cleaned or cleaned in {"-", "."}:
        raise ValueError("current_balance is not a valid monetary amount")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid monetary amount") from exc


def whole_days_open(opened, as_of):
    return (as_of - opened).days


def records_with_nonfinal_status(records, final_statuses):
    blocking = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            blocking.append({"index": index, "status": None, "reason": "malformed_record"})
            continue
        raw_status = record.get("status")
        status = raw_status.strip().lower() if isinstance(raw_status, str) else None
        if status not in final_statuses:
            blocking.append({"index": index, "status": raw_status, "reason": "nonfinal_or_unknown_status"})
    return blocking


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")

    blockers = []
    try:
        balance = parse_money(account.get("current_balance"))
        if balance != Decimal("0"):
            blockers.append({"code": "nonzero_balance", "current_balance": format(balance, ".2f")})
    except ValueError as exc:
        balance = None
        blockers.append({"code": "unknown_balance", "detail": str(exc)})

    try:
        opened = parse_date(account.get("date_of_account_open"))
        as_of = parse_date(payload.get("as_of"))
        age_days = whole_days_open(opened, as_of)
        if age_days < 60:
            blockers.append({"code": "account_too_new", "age_days": age_days, "minimum_days": 60})
    except ValueError as exc:
        age_days = None
        blockers.append({"code": "unknown_account_age", "detail": str(exc)})

    disputes = payload.get("disputes")
    if not isinstance(disputes, list):
        blockers.append({"code": "dispute_check_missing_or_invalid"})
    else:
        active_disputes = records_with_nonfinal_status(disputes, FINAL_DISPUTE_STATUSES)
        if active_disputes:
            blockers.append({"code": "active_or_unknown_disputes", "records": active_disputes})

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        blockers.append({"code": "replacement_order_check_missing_or_invalid"})
    else:
        pending_orders = records_with_nonfinal_status(orders, FINAL_ORDER_STATUSES)
        if pending_orders:
            blockers.append({"code": "pending_or_unknown_replacement_orders", "records": pending_orders})

    result = {
        "eligible": not blockers,
        "blockers": blockers,
        "account_age_days": age_days,
        "next_step": "may_check_retention_history" if not blockers else "resolve_or_recheck_blockers",
    }
    points = account.get("reward_points")
    if points is not None:
        try:
            decimal_points = Decimal(str(points))
            if decimal_points < 0:
                raise InvalidOperation
            result["reward_points"] = str(decimal_points)
            result["reward_cash_value"] = format(decimal_points / Decimal("100"), ".2f")
        except (InvalidOperation, ValueError):
            result["reward_cash_value_error"] = "reward_points must be a nonnegative number"
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(assess(payload), separators=(",", ":"), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible": False, "blockers": [{"code": "invalid_input", "detail": str(exc)}], "next_step": "supply_valid_input"}, separators=(",", ":")))


if __name__ == "__main__":
    main()
