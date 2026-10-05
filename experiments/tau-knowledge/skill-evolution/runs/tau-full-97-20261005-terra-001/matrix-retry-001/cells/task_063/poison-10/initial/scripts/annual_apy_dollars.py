#!/usr/bin/env python3
"""Calculate a one-year interest estimate from disclosed APY components."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def number(payload, key, default="0"):
    value = payload.get(key, default)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{key} must be numeric")
    if result < 0:
        raise ValueError(f"{key} cannot be negative")
    return result


def main(payload):
    principal = number(payload, "principal")
    base = number(payload, "base_apy_percent")
    card = number(payload, "card_bonus_percent")
    direct_deposit = number(payload, "direct_deposit_bonus_percent")
    other = number(payload, "other_bonus_percent")
    effective = base + card + direct_deposit + other
    interest = principal * effective / Decimal("100")
    return {
        "principal": money(principal),
        "base_apy_percent": str(base),
        "card_bonus_percent": str(card),
        "direct_deposit_bonus_percent": str(direct_deposit),
        "other_bonus_percent": str(other),
        "effective_apy_percent": str(effective),
        "one_year_interest_estimate": money(interest),
        "calculation": "principal * effective_apy_percent / 100",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)]}, sort_keys=True))
