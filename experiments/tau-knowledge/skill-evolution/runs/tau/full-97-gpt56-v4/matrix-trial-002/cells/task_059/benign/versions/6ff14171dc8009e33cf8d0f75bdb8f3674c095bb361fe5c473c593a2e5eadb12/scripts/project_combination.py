#!/usr/bin/env python3
"""Project one-year savings interest, card rewards, and known recurring costs.

Read one JSON object from stdin using the schema documented in SKILL.md. Emit one
JSON object to stdout. This helper performs no eligibility determination.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def number(data, key, default=None):
    value = data.get(key, default)
    if value is None:
        raise ValueError("missing required field: " + key)
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(key + " must be a number")
    if not decimal_value.is_finite() or decimal_value < 0:
        raise ValueError(key + " must be a finite nonnegative number")
    return decimal_value


def nested_number(data, parent, key):
    obj = data.get(parent)
    if not isinstance(obj, dict):
        raise ValueError(parent + " must be an object")
    return number(obj, key)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    balance = number(payload, "balance")
    spend_low = number(payload, "annual_spend_low")
    spend_high = number(payload, "annual_spend_high")
    if spend_high < spend_low:
        raise ValueError("annual_spend_high must be at least annual_spend_low")

    apy = nested_number(payload, "savings", "apy_percent")
    savings_fee = nested_number(payload, "savings", "annual_fee")
    cashback = nested_number(payload, "card", "cashback_percent")
    card_fee = nested_number(payload, "card", "annual_fee")
    other_cost = number(payload, "other_annual_cost", Decimal("0"))

    # APY is an annual effective yield. Daily accrual is already reflected in APY.
    interest = balance * apy / Decimal("100")
    rewards_low = spend_low * cashback / Decimal("100")
    rewards_high = spend_high * cashback / Decimal("100")
    known_costs = savings_fee + card_fee + other_cost
    net_low = interest + rewards_low - known_costs
    net_high = interest + rewards_high - known_costs

    return {
        "assumption": "APY is treated as an effective one-year yield on a stable balance; rewards apply only to eligible spend.",
        "annual_interest": money(interest),
        "annual_rewards_low": money(rewards_low),
        "annual_rewards_high": money(rewards_high),
        "known_annual_costs": money(known_costs),
        "net_one_year_low": money(net_low),
        "net_one_year_high": money(net_high),
        "rates_used": {
            "apy_percent": str(apy),
            "cashback_percent": str(cashback)
        }
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = main(json.loads(raw))
        print(json.dumps({"ok": True, "result": result}, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
