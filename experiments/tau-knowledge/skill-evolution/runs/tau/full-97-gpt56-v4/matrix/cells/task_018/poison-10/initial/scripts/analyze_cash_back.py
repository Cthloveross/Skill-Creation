#!/usr/bin/env python3
"""Calculate truncated cash-back points for structured transaction records.

Reads one JSON object from stdin and writes one JSON object to stdout.  This module
has no banking side effects and intentionally does not decide merchant eligibility.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from typing import Any

CENT = Decimal("0.01")


def decimal_value(value: Any, field: str) -> Decimal:
    """Return a finite non-negative Decimal, raising ValueError when invalid."""
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal value") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a finite non-negative decimal")
    return result


def expected_points(amount: Decimal, rate_percent: Decimal) -> int:
    """Cash-back points are cents of reward and fractional points are floored."""
    raw_points = amount * (rate_percent / Decimal("100")) / CENT
    return int(raw_points.to_integral_value(rounding=ROUND_FLOOR))


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    try:
        rate = decimal_value(payload.get("cash_back_rate_percent"), "cash_back_rate_percent")
    except ValueError as exc:
        return {"calculations": [], "mismatches": [], "errors": [{"field": "cash_back_rate_percent", "message": str(exc)}]}

    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return {"calculations": [], "mismatches": [], "errors": [{"field": "transactions", "message": "transactions must be an array"}]}

    calculations: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    for index, item in enumerate(transactions):
        if not isinstance(item, dict):
            errors.append({"index": index, "message": "transaction must be an object"})
            continue
        txn_id = item.get("transaction_id")
        if not isinstance(txn_id, str) or not txn_id.strip():
            errors.append({"index": index, "field": "transaction_id", "message": "transaction_id must be a non-empty string"})
            continue
        try:
            amount = decimal_value(item.get("amount"), "amount")
            awarded_raw = item.get("awarded_points")
            if isinstance(awarded_raw, bool):
                raise ValueError("awarded_points must be a non-negative whole number")
            awarded_decimal = decimal_value(awarded_raw, "awarded_points")
            if awarded_decimal != awarded_decimal.to_integral_value():
                raise ValueError("awarded_points must be a non-negative whole number")
        except ValueError as exc:
            errors.append({"transaction_id": txn_id, "message": str(exc)})
            continue

        status = item.get("status")
        completed = status is None or str(status).upper() == "COMPLETED"
        expected = expected_points(amount, rate)
        difference = expected - int(awarded_decimal)
        record = {
            "transaction_id": txn_id,
            "amount": format(amount, "f"),
            "cash_back_rate_percent": format(rate, "f"),
            "expected_points": expected,
            "awarded_points": int(awarded_decimal),
            "difference_points": difference,
            "difference_cash_back_dollars": format(Decimal(difference) * CENT, ".2f"),
            "status": status,
            "category": item.get("category"),
            "comparison_performed": completed,
        }
        if not completed:
            record["note"] = "Not treated as a mismatch because the transaction is not confirmed completed."
        elif difference != 0:
            mismatches.append(record)
        calculations.append(record)

    return {"calculations": calculations, "mismatches": mismatches, "errors": errors}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = analyze(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"calculations": [], "mismatches": [], "errors": [{"message": str(exc)}]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
