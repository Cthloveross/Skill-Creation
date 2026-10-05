#!/usr/bin/env python3
"""Calculate a posted-period savings-interest discrepancy from daily balances.

Reads JSON from stdin and emits JSON on stdout.
Input:
{
  "expected_apy": number,
  "actual_interest": number,
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": number}, ...],
  "known_actual_apy": number or null
}
The sequence must contain one consecutive day-end principal balance per day of the
actual interest period. APY is a percentage. The calculation uses an effective daily
rate derived from APY and a 365-day convention. Interest is rounded to cents only at
posting. If no known_actual_apy is supplied, the reported actual APY is an inferred
effective value that reproduces the posted amount under these inputs.
"""
import json
import math
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_daily_balances(records):
    if not isinstance(records, list) or not records:
        raise ValueError("daily_balances must be a nonempty array.")
    normalized = []
    prior = None
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each daily_balances item must be an object.")
        day = date.fromisoformat(str(record["date"]))
        balance = float(record["balance"])
        if not math.isfinite(balance) or balance < 0:
            raise ValueError("Each day-end balance must be a finite nonnegative number.")
        if prior is not None and day != prior + timedelta(days=1):
            raise ValueError("daily_balances dates must be consecutive calendar days.")
        normalized.append((day, balance))
        prior = day
    return normalized


def accrued_interest(balances, annual_apy):
    """Accrue with each day's principal and prior unposted accrued interest."""
    apy = float(annual_apy)
    if not math.isfinite(apy) or apy < 0:
        raise ValueError("APY must be a finite nonnegative percentage.")
    daily_factor = (1.0 + apy / 100.0) ** (1.0 / 365.0) - 1.0
    accrued = 0.0
    for _, principal in balances:
        accrued = (principal + accrued) * daily_factor
    return accrued


def infer_apy(balances, target):
    """Binary search a nonnegative APY that recreates target pre-rounding interest."""
    if target < 0:
        raise ValueError("actual_interest cannot be negative.")
    low, high = 0.0, 100.0
    while accrued_interest(balances, high) < target and high < 100000.0:
        high *= 2.0
    if accrued_interest(balances, high) < target:
        raise ValueError("Could not infer actual APY within supported range.")
    for _ in range(100):
        mid = (low + high) / 2.0
        if accrued_interest(balances, mid) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def main(payload):
    balances = validate_daily_balances(payload.get("daily_balances"))
    expected_apy = float(payload["expected_apy"])
    actual_interest = money(payload["actual_interest"])
    expected_raw = accrued_interest(balances, expected_apy)
    expected_interest = money(expected_raw)
    amount_difference = money(expected_interest - actual_interest)

    known = payload.get("known_actual_apy")
    if known is None:
        actual_apy = infer_apy(balances, float(actual_interest))
        actual_apy_source = "inferred_from_posted_interest"
    else:
        actual_apy = float(known)
        if not math.isfinite(actual_apy) or actual_apy < 0:
            raise ValueError("known_actual_apy must be a finite nonnegative percentage or null.")
        actual_apy_source = "verified_displayed_rate"

    result = {
        "actionable": amount_difference > Decimal("0.00"),
        "period_start": balances[0][0].isoformat(),
        "period_end": balances[-1][0].isoformat(),
        "days": len(balances),
        "expected_apy": round(expected_apy, 6),
        "actual_apy": round(actual_apy, 6),
        "actual_apy_source": actual_apy_source,
        "actual_interest": float(actual_interest),
        "expected_interest": float(expected_interest),
        "amount_difference": float(amount_difference),
        "calculation_convention": "daily compounding using effective APY / 365; rounded to cents at posting",
        "warnings": [],
    }
    if amount_difference == Decimal("0.00"):
        result["warnings"].append("No underpayment was found after cent rounding.")
    elif amount_difference < Decimal("0.00"):
        result["warnings"].append("Posted interest exceeds calculated interest; do not apply a negative credit.")
    if actual_apy_source == "inferred_from_posted_interest":
        result["warnings"].append("actual_apy is inferred; prefer an explicit displayed/applied rate if available.")
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"actionable": False, "error": str(exc)}))
