#!/usr/bin/env python3
"""Evaluate supplied credit-card closure facts; reads JSON stdin and writes JSON stdout."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "denied", "withdrawn", "cancelled", "canceled"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    text = value.strip()
    # Timestamps may be supplied for the as_of value.
    if field == "as_of":
        text = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")


def parse_money(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("current_balance must be a monetary number or string")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid monetary amount") from exc


def normalized_status(record: Any, collection: str) -> str | None:
    if not isinstance(record, dict):
        return None
    value = record.get("status")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    as_of = parse_date(payload.get("as_of"), "as_of")
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of")
    balance = parse_money(payload.get("current_balance"))
    age_days = (as_of - opened).days
    blockers: list[str] = []

    if balance != Decimal("0"):
        blockers.append("outstanding_balance_not_zero")
    if age_days < 60:
        blockers.append("account_under_60_days_old")

    disputes = payload.get("disputes", [])
    if disputes is None:
        blockers.append("dispute_status_unknown")
    elif not isinstance(disputes, list):
        raise ValueError("disputes must be an array or null")
    else:
        for record in disputes:
            if not isinstance(record, dict):
                blockers.append("dispute_record_ambiguous")
                break
            status = normalized_status(record, "disputes")
            if status is None:
                blockers.append("dispute_record_ambiguous")
                break
            if status not in FINAL_DISPUTE_STATUSES:
                if record.get("matches_target") is True:
                    blockers.append("target_account_has_pending_dispute")
                    break
                # A non-final dispute not proven unrelated is unsafe to ignore.
                blockers.append("nonfinal_dispute_account_association_unknown")
                break

    orders = payload.get("replacement_orders", [])
    if orders is None:
        blockers.append("replacement_order_status_unknown")
    elif not isinstance(orders, list):
        raise ValueError("replacement_orders must be an array or null")
    else:
        for record in orders:
            status = normalized_status(record, "replacement_orders")
            if status not in FINAL_REPLACEMENT_STATUSES:
                blockers.append("pending_or_ambiguous_replacement_order")
                break

    result: dict[str, Any] = {
        "eligible": not blockers,
        "blockers": blockers,
        "account_age_days": age_days,
        "balance_is_zero": balance == Decimal("0"),
    }

    annual_fee_date = payload.get("annual_fee_posted_date")
    if annual_fee_date is not None:
        fee_date = parse_date(annual_fee_date, "annual_fee_posted_date")
        fee_age = (as_of - fee_date).days
        result["annual_fee_age_days"] = fee_age
        result["annual_fee_full_refund_window"] = 0 <= fee_age <= 37

    points = payload.get("reward_points")
    if points is not None:
        try:
            points_decimal = Decimal(str(points))
        except InvalidOperation as exc:
            raise ValueError("reward_points must be numeric when supplied") from exc
        if points_decimal < 0:
            raise ValueError("reward_points cannot be negative")
        cash_value = (points_decimal * Decimal("0.01")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        result["reward_cash_value"] = f"${cash_value}"

    return result


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
