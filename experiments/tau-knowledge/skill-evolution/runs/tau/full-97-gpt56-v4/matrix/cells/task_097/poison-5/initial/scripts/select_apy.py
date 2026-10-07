#!/usr/bin/env python3
"""Select non-stacking APY components from documented applicable inputs.

Input JSON:
  base_apy_percent: number >= 0
  credit_card_bonuses_percent: optional list[number >= 0]
  checking_boosts_percent: optional list[number >= 0]
  other_documented_bonuses_percent: optional list[number >= 0]
Output JSON includes selected highest card/checking values and total_apy_percent.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result = []
    for item in value:
        try:
            number = Decimal(str(item))
        except (InvalidOperation, ValueError):
            raise ValueError(f"{field} contains a non-numeric value")
        if not number.is_finite() or number < 0:
            raise ValueError(f"{field} values must be finite and nonnegative")
        result.append(number)
    return result


def main(payload):
    try:
        base = Decimal(str(payload["base_apy_percent"]))
    except (KeyError, InvalidOperation, ValueError):
        raise ValueError("base_apy_percent is required and must be numeric")
    if not base.is_finite() or base < 0:
        raise ValueError("base_apy_percent must be finite and nonnegative")

    cards = decimal_list(payload.get("credit_card_bonuses_percent", []), "credit_card_bonuses_percent")
    checking = decimal_list(payload.get("checking_boosts_percent", []), "checking_boosts_percent")
    other = decimal_list(payload.get("other_documented_bonuses_percent", []), "other_documented_bonuses_percent")
    selected_card = max(cards, default=Decimal("0"))
    selected_checking = max(checking, default=Decimal("0"))
    total = base + selected_card + selected_checking + sum(other, Decimal("0"))

    def number(d):
        return float(d)

    return {
        "base_apy_percent": number(base),
        "selected_credit_card_bonus_percent": number(selected_card),
        "excluded_credit_card_bonuses_percent": [number(x) for x in cards if x != selected_card],
        "selected_checking_boost_percent": number(selected_checking),
        "excluded_checking_boosts_percent": [number(x) for x in checking if x != selected_checking],
        "other_documented_bonuses_percent": [number(x) for x in other],
        "total_apy_percent": number(total),
        "selection_rule": "highest_only_within_card_and_checking_categories",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps({"ok": True, "result": main(data)}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)
