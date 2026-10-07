#!/usr/bin/env python3
"""Compute a transparent stable-balance APY estimate from JSON stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def number(value, name, nonnegative=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a number")
    if not result.is_finite() or (nonnegative and result < 0):
        raise ValueError(f"{name} must be a finite nonnegative number")
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = number(payload.get("balance"), "balance")
    base = number(payload.get("base_apy_percent"), "base_apy_percent")
    relationship = number(payload.get("relationship_bonus_percent", 0), "relationship_bonus_percent")
    days = number(payload.get("days", 365), "days")
    bonuses = payload.get("bonuses_percent", [])
    if not isinstance(bonuses, list):
        raise ValueError("bonuses_percent must be an array")
    parsed_bonuses = [number(v, "bonuses_percent entry") for v in bonuses]
    nonzero = [v for v in parsed_bonuses if v != 0]
    if len(nonzero) > 1 and not payload.get("allow_multiple_card_bonuses", False):
        raise ValueError("multiple nonzero card bonuses are not allowed; select the highest applicable bonus")
    card_bonus = max(parsed_bonuses, default=Decimal("0"))
    apy = base + card_bonus + relationship
    interest = balance * (apy / Decimal("100")) * (days / Decimal("365"))
    cents = Decimal("0.01")
    return {
        "effective_apy_percent": float(apy),
        "selected_card_bonus_percent": float(card_bonus),
        "relationship_bonus_percent": float(relationship),
        "estimated_interest": float(interest.quantize(cents, rounding=ROUND_HALF_UP)),
        "estimated_ending_balance": float((balance + interest).quantize(cents, rounding=ROUND_HALF_UP)),
        "days": float(days),
        "note": "Estimate assumes a stable balance and treats the stated APY as an annual yield. Actual credited interest can vary with daily balances and qualification changes."
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
