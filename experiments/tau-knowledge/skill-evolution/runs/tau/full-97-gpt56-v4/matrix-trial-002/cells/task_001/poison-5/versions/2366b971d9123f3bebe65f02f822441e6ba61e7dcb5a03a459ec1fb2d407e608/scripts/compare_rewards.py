#!/usr/bin/env python3
"""Compare annual cash-back value from JSON received on stdin.

Input:
{
  "annual_spend": number|string,
  "cards": [{"name": string, "cashback_rate_percent": number|string,
             "annual_fee": number|string}]
}
Output is a JSON object containing calculations and pairwise break-even points.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def decimal_value(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative decimal, not boolean")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid decimal")
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError(f"{field} must be a non-negative finite decimal")
    return parsed


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    if "annual_spend" not in payload or "cards" not in payload:
        raise ValueError("annual_spend and cards are required")
    spend = decimal_value(payload["annual_spend"], "annual_spend")
    cards = payload["cards"]
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a non-empty array")

    calculated = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"cards[{index}] must be an object")
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"cards[{index}].name must be a non-empty string")
        rate = decimal_value(card.get("cashback_rate_percent"), f"cards[{index}].cashback_rate_percent")
        fee = decimal_value(card.get("annual_fee"), f"cards[{index}].annual_fee")
        gross = spend * rate / Decimal("100")
        net = gross - fee
        calculated.append({
            "name": name,
            "cashback_rate_percent": str(rate),
            "annual_fee": money(fee),
            "gross_rewards": money(gross),
            "net_value": money(net),
            "_rate": rate,
            "_fee": fee,
        })

    ranked = sorted(calculated, key=lambda item: (-item["_rate"] * spend / Decimal("100") + item["_fee"], item["name"]))
    pairwise = []
    for left_index in range(len(calculated)):
        for right_index in range(left_index + 1, len(calculated)):
            left = calculated[left_index]
            right = calculated[right_index]
            rate_difference = left["_rate"] - right["_rate"]
            if rate_difference == ZERO:
                threshold = None
            else:
                threshold_value = (left["_fee"] - right["_fee"]) * Decimal("100") / rate_difference
                threshold = None if threshold_value < ZERO else money(threshold_value)
            pairwise.append({
                "card_a": left["name"],
                "card_b": right["name"],
                "break_even_annual_spend": threshold,
            })

    for item in ranked:
        del item["_rate"]
        del item["_fee"]
    return {
        "annual_spend": money(spend),
        "cards_ranked_by_net_value": ranked,
        "pairwise_break_even_annual_spend": pairwise,
        "assumption": "All supplied annual spend is eligible purchase spend; estimates exclude interest, other fees, returns, and benefits outside cash back.",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
