#!/usr/bin/env python3
"""Calculate daily-compounded interest for a single homogeneous interval.

Input JSON:
  apy_percent: nonnegative number
  daily_balances: optional nonempty list of one end-of-day balance per day
  OR constant_daily_balance: number and day_count: positive integer
  apy_convention: optional 'effective_annual' (default) or 'nominal_annual'
Output JSON contains unrounded_interest and rounded_interest_cents.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
DAYS_PER_YEAR = Decimal("365")
CENT = Decimal("0.01")


def as_decimal(value, field, nonnegative=True):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not number.is_finite() or (nonnegative and number < 0):
        condition = "finite and nonnegative" if nonnegative else "finite"
        raise ValueError(f"{field} must be {condition}")
    return number


def balances_from(payload):
    has_list = "daily_balances" in payload
    has_constant = "constant_daily_balance" in payload or "day_count" in payload
    if has_list and has_constant:
        raise ValueError("provide daily_balances or constant_daily_balance with day_count, not both")
    if has_list:
        raw = payload["daily_balances"]
        if not isinstance(raw, list) or not raw:
            raise ValueError("daily_balances must be a nonempty list")
        return [as_decimal(x, "daily_balances item") for x in raw]
    if "constant_daily_balance" not in payload or "day_count" not in payload:
        raise ValueError("provide daily_balances or both constant_daily_balance and day_count")
    balance = as_decimal(payload["constant_daily_balance"], "constant_daily_balance")
    day_count = payload["day_count"]
    if isinstance(day_count, bool) or not isinstance(day_count, int) or day_count <= 0:
        raise ValueError("day_count must be a positive integer")
    return [balance] * day_count


def main(payload):
    apy = as_decimal(payload.get("apy_percent"), "apy_percent") / Decimal("100")
    convention = payload.get("apy_convention", "effective_annual")
    if convention == "effective_annual":
        daily_rate = (Decimal("1") + apy) ** (Decimal("1") / DAYS_PER_YEAR) - Decimal("1")
    elif convention == "nominal_annual":
        daily_rate = apy / DAYS_PER_YEAR
    else:
        raise ValueError("apy_convention must be effective_annual or nominal_annual")
    balances = balances_from(payload)
    # This sums per-day accruals on the documented daily balances. It does not
    # fabricate balance changes and leaves cross-interval compounding to the caller.
    interest = sum((balance * daily_rate for balance in balances), Decimal("0"))
    rounded = interest.quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "apy_percent": float(apy * Decimal("100")),
        "apy_convention": convention,
        "daily_rate": float(daily_rate),
        "days": len(balances),
        "unrounded_interest": float(interest),
        "rounded_interest_cents": float(rounded),
        "rounding": "ROUND_HALF_UP at final interval result; sum unrounded intervals before final statement rounding",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps({"ok": True, "result": main(data)}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)
