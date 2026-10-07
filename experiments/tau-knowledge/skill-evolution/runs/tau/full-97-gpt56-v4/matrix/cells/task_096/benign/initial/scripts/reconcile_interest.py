#!/usr/bin/env python3
"""Select non-stacking bonuses and model interest from JSON stdin.

All rate inputs are percentages (for example, 6.0 means 6.0%). The calculation
uses the nominal annual rate divided by 365 for daily accrual, compounded daily
when daily_compounding is true. This is a transparent estimate unless supplied
balances and cycle days are exact.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def bonus_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    values = [number(item, field) for item in value]
    if any(item < 0 for item in values):
        raise ValueError(f"{field} cannot contain negative values")
    return values


def decimal_json(value, places=None):
    if places is not None:
        value = value.quantize(places, rounding=ROUND_HALF_UP)
    return float(value)


def calculate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    for key in ("balance", "base_apy_percent", "days"):
        if key not in payload:
            raise ValueError(f"missing required field: {key}")

    balance = number(payload["balance"], "balance")
    base = number(payload["base_apy_percent"], "base_apy_percent")
    days_raw = payload["days"]
    if isinstance(days_raw, bool) or not isinstance(days_raw, int) or days_raw <= 0:
        raise ValueError("days must be a positive integer")
    if balance < 0 or base < 0:
        raise ValueError("balance and base_apy_percent cannot be negative")

    checking = bonus_list(payload.get("checking_boosts_percent", []), "checking_boosts_percent")
    cards = bonus_list(payload.get("card_bonuses_percent", []), "card_bonuses_percent")
    selected_checking = max(checking, default=Decimal("0"))
    selected_card = max(cards, default=Decimal("0"))
    total_apy = base + selected_checking + selected_card
    daily_compounding = payload.get("daily_compounding", True)
    if not isinstance(daily_compounding, bool):
        raise ValueError("daily_compounding must be a boolean")

    annual_rate = total_apy / Decimal("100")
    if daily_compounding:
        # Decimal has no portable fractional exponent; float is sufficient for
        # a displayed currency estimate, then converted back for rounding.
        factor = Decimal(str(math.pow(float(Decimal("1") + annual_rate / Decimal("365")), days_raw) - 1))
    else:
        factor = annual_rate * Decimal(days_raw) / Decimal("365")
    interest = balance * factor

    result = {
        "selected_checking_boost_percent": decimal_json(selected_checking),
        "selected_card_bonus_percent": decimal_json(selected_card),
        "total_apy_percent": decimal_json(total_apy),
        "modeled_interest": decimal_json(interest, CENT),
        "calculation_basis": {
            "balance": decimal_json(balance, CENT),
            "days": days_raw,
            "daily_compounding": daily_compounding,
            "note": "Uses the highest eligible checking boost and highest eligible card bonus; input arrays must contain eligible bonuses only."
        }
    }
    if "posted_interest" in payload and payload["posted_interest"] is not None:
        posted = number(payload["posted_interest"], "posted_interest")
        if posted < 0:
            raise ValueError("posted_interest cannot be negative")
        result["posted_interest"] = decimal_json(posted, CENT)
        result["difference_modeled_minus_posted"] = decimal_json(interest - posted, CENT)
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps({"ok": True, "result": calculate(payload)}, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))


if __name__ == "__main__":
    main()
