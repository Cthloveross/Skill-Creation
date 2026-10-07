#!/usr/bin/env python3
"""Estimate daily-compounded interest from an explicit daily-balance series.

Reads JSON from stdin and emits JSON to stdout. This helper performs no bank action.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
DAYS_PER_YEAR = Decimal("365")


def error(message):
    print(json.dumps({"status": "error", "error": message}, separators=(",", ":")))
    return 2


def decimal_value(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal number or string")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} is not a valid decimal")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return error("stdin must contain one JSON object")
    if not isinstance(payload, dict):
        return error("input must be a JSON object")

    rows = payload.get("daily_balances")
    contiguous = payload.get("require_contiguous_dates", True)
    if not isinstance(rows, list) or not rows:
        return error("daily_balances must be a nonempty array")
    if not isinstance(contiguous, bool):
        return error("require_contiguous_dates must be boolean")

    parsed = []
    seen = set()
    try:
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"daily_balances[{index}] must be an object")
            raw_date = row.get("date")
            if not isinstance(raw_date, str):
                raise ValueError(f"daily_balances[{index}].date must be YYYY-MM-DD")
            try:
                day = date.fromisoformat(raw_date)
            except ValueError:
                raise ValueError(f"daily_balances[{index}].date must be YYYY-MM-DD")
            if day in seen:
                raise ValueError("daily_balances dates must be unique")
            seen.add(day)
            balance = decimal_value(row.get("balance"), f"daily_balances[{index}].balance")
            apy = decimal_value(row.get("apy_percent"), f"daily_balances[{index}].apy_percent")
            if balance < 0:
                raise ValueError(f"daily_balances[{index}].balance must not be negative")
            if apy < 0:
                raise ValueError(f"daily_balances[{index}].apy_percent must not be negative")
            parsed.append((day, balance, apy))
    except ValueError as exc:
        return error(str(exc))

    dates = [entry[0] for entry in parsed]
    if dates != sorted(dates):
        return error("daily_balances must be in ascending date order")
    gaps = []
    for previous, current in zip(dates, dates[1:]):
        if current != previous + timedelta(days=1):
            gaps.append({"after": previous.isoformat(), "before": current.isoformat()})
    if contiguous and gaps:
        return error("daily_balances must contain every calendar day when require_contiguous_dates is true")

    total = Decimal("0")
    by_apy = {}
    for _, balance, apy in parsed:
        # APY is treated as an effective annual yield, so this is its daily
        # compounding-equivalent periodic rate.
        daily_rate = (Decimal("1") + apy / Decimal("100")) ** (Decimal("1") / DAYS_PER_YEAR) - Decimal("1")
        accrual = balance * daily_rate
        total += accrual
        key = format(apy, "f")
        by_apy.setdefault(key, {"days": 0, "unrounded_interest": Decimal("0")})
        by_apy[key]["days"] += 1
        by_apy[key]["unrounded_interest"] += accrual

    subtotals = []
    for apy, values in sorted(by_apy.items(), key=lambda item: Decimal(item[0])):
        subtotals.append({
            "apy_percent": apy,
            "days": values["days"],
            "unrounded_interest": format(values["unrounded_interest"], "f"),
        })
    result = {
        "status": "ok",
        "days": len(parsed),
        "start_date": dates[0].isoformat(),
        "end_date": dates[-1].isoformat(),
        "partial_period": bool(gaps),
        "gaps": gaps,
        "unrounded_interest": format(total, "f"),
        "cycle_interest_rounded_cents": format(total.quantize(CENT, rounding=ROUND_HALF_UP), "f"),
        "subtotals_by_apy": subtotals,
        "assumption": "APY is treated as an effective annual yield and converted to a daily periodic rate using (1 + APY/100) ** (1/365) - 1; rounding is applied once to the total.",
    }
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
