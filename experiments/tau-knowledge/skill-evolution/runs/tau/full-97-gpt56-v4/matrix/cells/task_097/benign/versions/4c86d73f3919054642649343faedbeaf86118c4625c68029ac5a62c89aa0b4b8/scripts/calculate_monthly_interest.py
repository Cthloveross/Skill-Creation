#!/usr/bin/env python3
"""Calculate a constant-balance monthly interest comparison.

Read one JSON object on stdin and write JSON on stdout.  APYs are percentages and
this helper is only for an evidenced annual-APY-divided-by-twelve posting method.
It never accesses accounts or performs banking actions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")

def number(value, name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{name} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result

def cents(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def main(data):
    balance = number(data.get("balance"), "balance")
    expected = number(data.get("expected_apy"), "expected_apy")
    actual = number(data.get("actual_apy"), "actual_apy")
    if balance < 0 or expected < 0 or actual < 0:
        raise ValueError("balance and APYs must not be negative")
    expected_interest = balance * expected / Decimal("100") / Decimal("12")
    actual_interest = balance * actual / Decimal("100") / Decimal("12")
    difference = cents(expected_interest) - cents(actual_interest)
    return {"ok": True, "balance": format(balance, "f"),
            "expected_apy": format(expected, "f"), "actual_apy": format(actual, "f"),
            "expected_interest_rounded_to_cents": format(cents(expected_interest), "f"),
            "actual_interest_rounded_to_cents": format(cents(actual_interest), "f"),
            "difference_rounded_to_cents": format(difference, "f"),
            "positive_correction_indicated": difference > 0}

if __name__ == "__main__":
    try:
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(value), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
