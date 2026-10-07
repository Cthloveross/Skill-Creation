#!/usr/bin/env python3
"""Rank savings/card combinations by constant-balance one-year net earnings.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the public schema. This program is advisory only and performs no bank action.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
PCT = Decimal("0.0001")


def decimal_value(value, field, default=Decimal("0")):
    """Parse a finite, nonnegative Decimal used by this calculator."""
    if value is None:
        return default
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not a boolean")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid number")
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return parsed


def bonus_values(value, field):
    """Normalize a scalar or list of APY percentage-point bonuses."""
    if value is None:
        return []
    raw_values = value if isinstance(value, list) else [value]
    return [decimal_value(item, f"{field}[{index}]") for index, item in enumerate(raw_values)]


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def percent(value):
    return format(value.quantize(PCT, rounding=ROUND_HALF_UP), ".4f")


def analyze_candidate(candidate, deposit, index):
    if not isinstance(candidate, dict):
        raise ValueError(f"combinations[{index}] must be an object")
    savings_name = candidate.get("savings_name")
    if not isinstance(savings_name, str) or not savings_name.strip():
        raise ValueError(f"combinations[{index}].savings_name is required")
    card_name = candidate.get("card_name")
    if card_name is not None and not isinstance(card_name, str):
        raise ValueError(f"combinations[{index}].card_name must be a string or null")

    base = decimal_value(candidate.get("base_apy_pct"), f"combinations[{index}].base_apy_pct")
    opening_minimum = decimal_value(candidate.get("opening_minimum"), f"combinations[{index}].opening_minimum")
    ongoing_minimum = decimal_value(candidate.get("ongoing_minimum"), f"combinations[{index}].ongoing_minimum")
    checking_values = bonus_values(candidate.get("checking_boosts_pct"), f"combinations[{index}].checking_boosts_pct")
    card_values = bonus_values(candidate.get("card_apy_bonuses_pct"), f"combinations[{index}].card_apy_bonuses_pct")
    relationship = decimal_value(candidate.get("relationship_bonus_pct"), f"combinations[{index}].relationship_bonus_pct")
    other_values = bonus_values(candidate.get("other_additive_bonuses_pct"), f"combinations[{index}].other_additive_bonuses_pct")
    card_fee = decimal_value(candidate.get("annual_card_fee"), f"combinations[{index}].annual_card_fee")
    savings_fee = decimal_value(candidate.get("annual_savings_fee"), f"combinations[{index}].annual_savings_fee")
    conditions = candidate.get("conditions", [])
    if not isinstance(conditions, list) or not all(isinstance(x, str) for x in conditions):
        raise ValueError(f"combinations[{index}].conditions must be an array of strings")

    selected_checking = max(checking_values, default=Decimal("0"))
    selected_card = max(card_values, default=Decimal("0"))
    other_total = sum(other_values, Decimal("0"))
    total_apy = base + selected_checking + selected_card + relationship + other_total
    fees = card_fee + savings_fee
    shortfalls = []
    if deposit < opening_minimum:
        shortfalls.append("deposit is below opening minimum")
    if deposit < ongoing_minimum:
        shortfalls.append("deposit is below ongoing minimum")

    result = {
        "input_index": index,
        "savings_name": savings_name,
        "card_name": card_name,
        "deposit_amount": money(deposit),
        "opening_minimum": money(opening_minimum),
        "ongoing_minimum": money(ongoing_minimum),
        "base_apy_pct": percent(base),
        "selected_checking_boost_pct": percent(selected_checking),
        "selected_card_bonus_pct": percent(selected_card),
        "relationship_bonus_pct": percent(relationship),
        "other_additive_bonus_total_pct": percent(other_total),
        "total_apy_pct": percent(total_apy),
        "annual_card_fee": money(card_fee),
        "annual_savings_fee": money(savings_fee),
        "annual_fees": money(fees),
        "conditions": conditions,
    }
    if shortfalls:
        result["status"] = "infeasible"
        result["reasons"] = shortfalls
    else:
        gross_interest = deposit * total_apy / Decimal("100")
        net = gross_interest - fees
        result.update({
            "status": "feasible",
            "gross_one_year_interest": money(gross_interest),
            "net_one_year": money(net),
        })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        deposit = decimal_value(payload.get("deposit_amount"), "deposit_amount")
        combinations = payload.get("combinations")
        if not isinstance(combinations, list) or not combinations:
            raise ValueError("combinations must be a nonempty array")
        analyzed = [analyze_candidate(item, deposit, i) for i, item in enumerate(combinations)]
        feasible = [item for item in analyzed if item["status"] == "feasible"]
        infeasible = [item for item in analyzed if item["status"] == "infeasible"]
        feasible.sort(key=lambda item: (-Decimal(item["net_one_year"]), item["input_index"]))
        recommendation = feasible[0] if feasible else None
        print(json.dumps({
            "calculation_assumptions": [
                "APY is treated as the one-year yield for a constant balance.",
                "Only the highest supplied card bonus and highest supplied checking boost are selected.",
                "Only supplied annual fees are subtracted.",
            ],
            "feasible_ranked": feasible,
            "infeasible": infeasible,
            "recommendation": recommendation,
        }, ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
