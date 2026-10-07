#!/usr/bin/env python3
"""Calculate a daily-compounded savings-interest audit from JSON stdin.

Input schema:
{
  "base_apy": number,
  "qualifying_checking_boosts": [number, ...],
  "active_card_bonuses": [number, ...],
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": number}, ...],
  "actual_interest": number (optional),
  "actual_apy": number (optional)
}

Exactly one of actual_interest or actual_apy is normally needed. If actual_apy is
provided, actual interest is calculated from the same daily balances. If both are
provided, actual_interest is used as the posted amount and actual_apy is retained.
Output is a JSON object with either status="ok" or status="error".
"""
import json
import math
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def daily_rate(apy):
    return math.pow(1.0 + float(apy) / 100.0, 1.0 / 365.0) - 1.0


def compound_interest(balances, apy):
    """Accrue interest daily, including prior days' accrued interest."""
    rate = daily_rate(apy)
    accrued = 0.0
    for balance in balances:
        accrued = (float(balance) + accrued) * rate
    return accrued


def implied_apy(balances, interest):
    """Solve for the effective annual APY yielding the supplied interest."""
    target = float(interest)
    if target < 0:
        raise ValueError("actual_interest cannot be negative")
    lo, hi = 0.0, 100.0
    while compound_interest(balances, hi) < target and hi < 100000.0:
        hi *= 2.0
    if compound_interest(balances, hi) < target:
        raise ValueError("actual_interest is outside the supported APY search range")
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if compound_interest(balances, mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def fail(message):
    print(json.dumps({"status": "error", "message": message}))
    raise SystemExit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        fail("invalid JSON input: %s" % exc)

    required = ("base_apy", "qualifying_checking_boosts", "active_card_bonuses", "daily_balances")
    missing = [key for key in required if key not in data]
    if missing:
        fail("missing required fields: " + ", ".join(missing))
    if "actual_interest" not in data and "actual_apy" not in data:
        fail("provide actual_interest or actual_apy")

    try:
        base = float(data["base_apy"])
        checks = [float(x) for x in data["qualifying_checking_boosts"]]
        cards = [float(x) for x in data["active_card_bonuses"]]
        raw_days = data["daily_balances"]
        if base < 0 or any(x < 0 for x in checks + cards):
            raise ValueError("APY values must be non-negative")
        if not raw_days:
            raise ValueError("daily_balances must not be empty")
        dates, balances = [], []
        for item in raw_days:
            dates.append(date.fromisoformat(item["date"]))
            balance = float(item["balance"])
            if balance < 0:
                raise ValueError("daily balances must be non-negative")
            balances.append(balance)
        for prior, following in zip(dates, dates[1:]):
            if following != prior + timedelta(days=1):
                raise ValueError("daily balance dates must be consecutive")
    except (KeyError, TypeError, ValueError) as exc:
        fail("invalid calculation input: %s" % exc)

    selected_check = max(checks) if checks else 0.0
    selected_card = max(cards) if cards else 0.0
    expected_apy = base + selected_check + selected_card
    expected_interest_raw = compound_interest(balances, expected_apy)

    try:
        actual_apy = float(data["actual_apy"]) if "actual_apy" in data else None
        if actual_apy is not None and actual_apy < 0:
            raise ValueError("actual_apy must be non-negative")
        if "actual_interest" in data:
            actual_interest_raw = float(data["actual_interest"])
            if actual_interest_raw < 0:
                raise ValueError("actual_interest must be non-negative")
            if actual_apy is None:
                actual_apy = implied_apy(balances, actual_interest_raw)
        else:
            actual_interest_raw = compound_interest(balances, actual_apy)
    except (TypeError, ValueError) as exc:
        fail("invalid actual-interest input: %s" % exc)

    expected_interest = money(expected_interest_raw)
    actual_interest = money(actual_interest_raw)
    correction = money(expected_interest - actual_interest)
    output = {
        "status": "ok",
        "period_start": dates[0].isoformat(),
        "period_end": dates[-1].isoformat(),
        "days": len(balances),
        "selected_checking_boost_apy": selected_check,
        "selected_card_bonus_apy": selected_card,
        "expected_apy": round(expected_apy, 10),
        "actual_apy": round(actual_apy, 10),
        "expected_interest": float(expected_interest),
        "actual_interest": float(actual_interest),
        "amount_difference": float(correction),
        "ready_for_correction": correction > Decimal("0.00"),
        "method": "daily compounding from effective annual APY; highest checking and card bonus selected independently"
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
