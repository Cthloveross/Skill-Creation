#!/usr/bin/env python3
"""Advisory, deterministic credit-card closure eligibility evaluator.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
never calls banking tools and does not authorize any action.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a non-empty ISO date or datetime string")
    text = value.strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("must be an ISO date or datetime") from exc


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("balance must be numeric, not boolean")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError("balance is not a valid currency amount") from exc
    raise ValueError("balance is required")


def require_bool(data, field, blockers):
    value = data.get(field)
    if value is not True:
        label = field.replace("_", " ")
        blockers.append(f"{label} is not confirmed")
        return False
    return True


def evaluate(data):
    blockers = []
    operational_blockers = []

    try:
        as_of = parse_date(data.get("as_of"))
        opened_on = parse_date(data.get("opened_on"))
        age_days = (as_of - opened_on).days
        if age_days < 0:
            blockers.append("account opening date is after the evaluation date")
        elif age_days < 60:
            blockers.append("account has been open fewer than 60 days")
    except ValueError as exc:
        age_days = None
        blockers.append(f"account age cannot be evaluated: {exc}")

    try:
        balance = parse_money(data.get("balance"))
        if balance != Decimal("0"):
            blockers.append("outstanding balance is not exactly $0.00")
    except ValueError as exc:
        balance = None
        blockers.append(f"balance cannot be evaluated: {exc}")

    disputes = data.get("pending_disputes")
    if disputes is not False:
        blockers.append("pending-dispute status is not confirmed clear")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        blockers.append("replacement-order status is not checked")
    else:
        nonfinal = []
        for index, order in enumerate(orders):
            status = order.get("status") if isinstance(order, dict) else None
            normalized = status.strip().lower() if isinstance(status, str) else ""
            if normalized not in FINAL_REPLACEMENT_STATUSES:
                nonfinal.append(index)
        if nonfinal:
            blockers.append("one or more replacement orders are pending, non-final, or ambiguous")

    for field in (
        "identity_verified",
        "authority_verified",
        "ownership_verified",
        "product_confirmed",
        "final_confirmation",
    ):
        if not require_bool(data, field, operational_blockers):
            pass

    result = {
        "closure_eligible": not blockers,
        "operationally_ready": not blockers and not operational_blockers,
        "account_age_days": age_days,
        "blockers": blockers + operational_blockers,
    }

    points = data.get("reward_points")
    cash_back_points = data.get("cash_back_points", False)
    if points is not None:
        if isinstance(points, bool) or not isinstance(points, int) or points < 0:
            result["reward_points_error"] = "reward_points must be a nonnegative integer"
        elif cash_back_points is True:
            result["cash_back_reward_value"] = format(Decimal(points) * Decimal("0.01"), ".2f")
            result["cash_back_reward_currency"] = "USD"
        elif cash_back_points is not False:
            result["reward_points_error"] = "cash_back_points must be boolean when supplied"

    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = evaluate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {
            "closure_eligible": False,
            "operationally_ready": False,
            "account_age_days": None,
            "blockers": [f"invalid evaluator input: {exc}"],
        }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
