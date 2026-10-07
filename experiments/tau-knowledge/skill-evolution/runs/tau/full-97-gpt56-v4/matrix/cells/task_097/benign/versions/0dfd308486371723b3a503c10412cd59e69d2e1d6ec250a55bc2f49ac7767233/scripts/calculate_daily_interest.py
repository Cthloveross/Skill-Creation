#!/usr/bin/env python3
"""Calculate a daily-compounded interest segment from verified daily data.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs
no account access and never triggers a bank action.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def main(payload):
    rate = dec(payload.get("daily_rate"), "daily_rate")
    if rate < 0:
        raise ValueError("daily_rate must not be negative")
    days = payload.get("days")
    if not isinstance(days, list) or not days:
        raise ValueError("days must be a non-empty list")
    round_daily = payload.get("round_daily_interest_to_cents", False)
    if not isinstance(round_daily, bool):
        raise ValueError("round_daily_interest_to_cents must be boolean")

    prior_date = None
    accrued = Decimal("0")
    total_principal_days = Decimal("0")
    for index, item in enumerate(days):
        if not isinstance(item, dict):
            raise ValueError(f"days[{index}] must be an object")
        raw_date = item.get("date")
        try:
            parsed_date = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            raise ValueError(f"days[{index}].date must be YYYY-MM-DD")
        if prior_date is not None and parsed_date != prior_date.fromordinal(prior_date.toordinal() + 1):
            raise ValueError("days must contain consecutive calendar dates")
        prior_date = parsed_date
        balance = dec(item.get("end_of_day_balance"), f"days[{index}].end_of_day_balance")
        if balance < 0:
            raise ValueError("end_of_day_balance must not be negative")
        total_principal_days += balance
        daily_interest = (balance + accrued) * rate
        if round_daily:
            daily_interest = money(daily_interest)
        accrued += daily_interest

    result = {
        "ok": True,
        "days_processed": len(days),
        "daily_rate": format(rate, "f"),
        "principal_balance_days": format(total_principal_days, "f"),
        "expected_interest_unrounded": format(accrued, "f"),
        "expected_interest_rounded_to_cents": format(money(accrued), "f"),
        "daily_rounding_used": round_daily,
    }
    if "actual_interest" in payload and payload["actual_interest"] is not None:
        actual = dec(payload["actual_interest"], "actual_interest")
        difference = accrued - actual
        result["actual_interest"] = format(actual, "f")
        result["difference_unrounded"] = format(difference, "f")
        result["difference_rounded_to_cents"] = format(money(difference), "f")
        result["positive_correction_indicated"] = money(difference) > 0
    return result


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":")))
    except Exception as exc:  # JSON error permits callers to fail safely.
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
