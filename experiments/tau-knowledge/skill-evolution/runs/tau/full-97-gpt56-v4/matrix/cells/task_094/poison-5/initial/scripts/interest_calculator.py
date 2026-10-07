#!/usr/bin/env python3
"""Calculate a daily-compounded savings-interest discrepancy.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no banking actions and intentionally does not choose APY components.
"""
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def num(value, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def derive_apy(balances, actual: Decimal, basis: int) -> float | None:
    # Interest is monotonic in APY for nonnegative balances. Bisection avoids
    # assuming a constant balance and is adequate for report review.
    if actual == 0:
        return 0.0
    if all(b == 0 for b in balances):
        return None
    target = float(actual)

    def accrued(apy_percent: float) -> float:
        daily = math.pow(1.0 + apy_percent / 100.0, 1.0 / basis) - 1.0
        return sum(float(b) * daily for b in balances)

    low, high = 0.0, 100.0
    while accrued(high) < target and high < 1_000_000:
        high *= 2.0
    if accrued(high) < target:
        return None
    for _ in range(100):
        mid = (low + high) / 2.0
        if accrued(mid) < target:
            low = mid
        else:
            high = mid
    return round((low + high) / 2.0, 8)


def main(data: dict) -> dict:
    required = {"expected_apy", "daily_balances", "actual_interest"}
    missing = sorted(required - set(data))
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    expected_apy = num(data["expected_apy"], "expected_apy")
    actual = num(data["actual_interest"], "actual_interest")
    if expected_apy < 0:
        raise ValueError("expected_apy cannot be negative")
    if actual < 0:
        raise ValueError("actual_interest cannot be negative")
    balances_value = data["daily_balances"]
    if not isinstance(balances_value, list) or not balances_value:
        raise ValueError("daily_balances must be a nonempty array")
    balances = [num(x, "daily_balances item") for x in balances_value]
    if any(x < 0 for x in balances):
        raise ValueError("daily_balances cannot contain negative values")
    basis = data.get("day_count_basis", 365)
    if isinstance(basis, bool) or not isinstance(basis, int) or basis <= 0:
        raise ValueError("day_count_basis must be a positive integer")
    rounding = data.get("rounding", "end")
    if rounding not in {"end", "daily_cents"}:
        raise ValueError("rounding must be 'end' or 'daily_cents'")

    daily_rate = (Decimal(1) + expected_apy / Decimal(100)) ** (Decimal(1) / Decimal(basis)) - Decimal(1)
    daily_accruals = [balance * daily_rate for balance in balances]
    if rounding == "daily_cents":
        expected = sum((money(x) for x in daily_accruals), Decimal(0))
    else:
        expected = money(sum(daily_accruals, Decimal(0)))
    actual_rounded = money(actual)
    difference = money(expected - actual_rounded)
    derived = derive_apy(balances, actual_rounded, basis)
    warnings = []
    if actual != actual_rounded:
        warnings.append("actual_interest was rounded to cents for comparison")
    if expected_apy == 0:
        warnings.append("Expected APY is zero; confirm this is intended.")
    if any(x == 0 for x in balances):
        warnings.append("One or more daily balances are zero; verify the balance timeline.")

    return {
        "days": len(balances),
        "day_count_basis": basis,
        "rounding": rounding,
        "expected_apy": float(expected_apy),
        "daily_rate": float(daily_rate),
        "expected_interest": float(expected),
        "actual_interest": float(actual_rounded),
        "amount_difference": float(difference),
        "has_discrepancy": difference > 0,
        "derived_actual_apy": derived,
        "validation_messages": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":"), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
