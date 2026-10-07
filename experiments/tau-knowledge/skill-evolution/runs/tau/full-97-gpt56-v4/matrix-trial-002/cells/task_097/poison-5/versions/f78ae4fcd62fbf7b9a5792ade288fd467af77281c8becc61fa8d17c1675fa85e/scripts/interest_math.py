#!/usr/bin/env python3
"""Calculate a savings interest correction from authoritative daily entries.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input:
  {
    "daily_entries": [
      {"date": "YYYY-MM-DD", "balance": number, "expected_apy": number}, ...
    ],
    "actual_interest": number,
    "days_in_year": 365
  }
`daily_entries` must contain one entry per applicable accrual day. APY is a
percentage, e.g. 4.5 means 4.5%. Entries are end-of-day principal
balances before the calculation's accrued interest is added. Values are not
rounded per day.
Output always contains `valid`, `errors`, and, when valid, cent-rounded
expected_interest, actual_interest, and amount_difference.
"""

import json
import math
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate(payload):
    errors = []
    entries = payload.get("daily_entries")
    actual = payload.get("actual_interest")
    days_in_year = payload.get("days_in_year", 365)

    if not isinstance(entries, list) or not entries:
        errors.append("daily_entries must be a non-empty list")
    try:
        actual_decimal = Decimal(str(actual))
        if not actual_decimal.is_finite():
            raise ValueError
    except Exception:
        errors.append("actual_interest must be a finite number")
        actual_decimal = Decimal("0")
    if not isinstance(days_in_year, int) or days_in_year <= 0:
        errors.append("days_in_year must be a positive integer")

    seen_dates = set()
    parsed_dates = []
    total = Decimal("0")
    if isinstance(entries, list):
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                errors.append(f"daily_entries[{index}] must be an object")
                continue
            try:
                entry_date = date.fromisoformat(str(entry["date"]))
                if entry_date in seen_dates:
                    errors.append(f"duplicate date: {entry_date.isoformat()}")
                seen_dates.add(entry_date)
                parsed_dates.append(entry_date)
            except Exception:
                errors.append(f"daily_entries[{index}].date must be YYYY-MM-DD")
            try:
                balance = Decimal(str(entry["balance"]))
                apy = Decimal(str(entry["expected_apy"]))
                if not balance.is_finite() or not apy.is_finite():
                    raise ValueError
                if balance < 0:
                    errors.append(f"daily_entries[{index}].balance cannot be negative")
                if apy <= Decimal("-100"):
                    errors.append(f"daily_entries[{index}].expected_apy must exceed -100")
                # Decimal exponentiation with a fractional exponent is not
                # portable, so use float only for the compounding factor.
                daily_factor = Decimal(str((1.0 + float(apy) / 100.0) ** (1.0 / days_in_year)))
                # The supplied balance is the day's principal/end-of-day
                # balance before adding this calculation's accrued interest.
                # Carry the previously accrued interest so a constant balance
                # receives true daily compounding; daily balance changes still
                # govern the principal on which that day accrues.
                total = (balance + total) * daily_factor - balance
            except KeyError as exc:
                errors.append(f"daily_entries[{index}] missing {exc.args[0]}")
            except (ValueError, TypeError, ArithmeticError):
                errors.append(f"daily_entries[{index}] has invalid balance or expected_apy")

    if not errors and len(parsed_dates) > 1:
        ordered = sorted(parsed_dates)
        for previous, following in zip(ordered, ordered[1:]):
            if (following - previous).days != 1:
                errors.append(
                    "daily_entries must contain one consecutive entry for each accrual day"
                )
                break

    if errors:
        return {"valid": False, "errors": errors}

    expected = money(total)
    actual_out = money(actual_decimal)
    difference = money(expected - actual_out)
    return {
        "valid": True,
        "errors": [],
        "expected_interest": float(expected),
        "actual_interest": float(actual_out),
        "amount_difference": float(difference),
        "credit_authorized_by_calculation": difference > Decimal("0"),
        "note": "A positive result still requires verified ownership, exact transaction evidence, and documented APY eligibility before a banking action."
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        output = calculate(payload)
    except Exception as exc:
        output = {"valid": False, "errors": [str(exc)]}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
