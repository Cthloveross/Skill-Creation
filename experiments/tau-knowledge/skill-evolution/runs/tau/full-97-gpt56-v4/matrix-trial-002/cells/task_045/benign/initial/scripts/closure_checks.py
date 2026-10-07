#!/usr/bin/env python3
"""Summarize static credit-card closure eligibility from JSON stdin.

This helper is intentionally side-effect free. Runtime tools remain the authority for
account state, disputes, replacement orders, payments, and closure.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a nonempty date string")
    value = value.strip()
    # Accept ISO dates and common timestamps where the first ten characters are ISO.
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("must be YYYY-MM-DD, an ISO timestamp, MM/DD/YYYY, or YYYY/MM/DD")


def decimal_value(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def main(payload):
    errors = []
    blockers = []
    account_age_days = None

    try:
        opened = parse_date(payload.get("account_open_date"))
        current = parse_date(payload.get("current_date"))
        account_age_days = (current - opened).days
        if account_age_days < 0:
            errors.append("current_date precedes account_open_date")
        elif account_age_days < 60:
            blockers.append("account_age_under_60_days")
    except ValueError as exc:
        errors.append("account_open_date/current_date: " + str(exc))

    try:
        balance = decimal_value(payload.get("balance"), "balance")
        if balance != Decimal("0"):
            blockers.append("nonzero_balance")
    except ValueError as exc:
        errors.append(str(exc))

    dispute = payload.get("has_active_or_pending_dispute")
    if not isinstance(dispute, bool):
        errors.append("has_active_or_pending_dispute must be boolean")
    elif dispute:
        blockers.append("active_or_pending_dispute")

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        errors.append("replacement_orders must be a list")
    else:
        for order in orders:
            status = order.get("status") if isinstance(order, dict) else None
            if not isinstance(status, str) or status.strip().lower() not in FINAL_REPLACEMENT_STATUSES:
                blockers.append("pending_or_ambiguous_replacement_order")
                break

    result = {
        "account_age_days": account_age_days,
        "blockers": blockers,
        "errors": errors,
        "eligible": not errors and not blockers,
    }

    if "reward_points" in payload:
        try:
            points = decimal_value(payload["reward_points"], "reward_points")
            if points < 0:
                raise ValueError("reward_points must not be negative")
            result["cash_back_value_dollars"] = str(
                (points * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
        except ValueError as exc:
            result["errors"].append(str(exc))
            result["eligible"] = False

    return result


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible": False, "blockers": [], "errors": [str(exc)]}, sort_keys=True))
        sys.exit(2)
