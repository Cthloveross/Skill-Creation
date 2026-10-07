#!/usr/bin/env python3
"""Compare documented savings-APY scenarios.

Input JSON:
{
  "deposit_amount": "6000",
  "candidates": [{
    "name": "label",
    "base_apy": "5.5",
    "minimum_balance": "5000",
    "checking_boosts": [{"source": "Checking Account", "apy": "0.75"}],
    "credit_card_bonuses": [{"source": "Card", "apy": "0.60"}],
    "other_additive_bonuses": [{"source": "documented independent bonus", "apy": "0"}]
  }]
}

APY values are percentage points, not decimal fractions. Output JSON identifies eligible
scenarios, the selected non-stacking bonuses, and total APY. This script does not establish
that a card, account, rate, or balance requirement is actually available to a customer.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if number < 0:
        raise ValueError(f"{field} cannot be negative")
    return number


def clean(number):
    text = format(number.normalize(), "f")
    return "0" if text in ("-0", "") else text


def highest(items, label):
    if items is None:
        return {"source": None, "apy": Decimal("0")}
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    normalized = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        normalized.append({
            "source": str(item.get("source", "unspecified")),
            "apy": decimal_value(item.get("apy", "0"), f"{label}[{index}].apy"),
        })
    if not normalized:
        return {"source": None, "apy": Decimal("0")}
    return max(normalized, key=lambda item: item["apy"])


def main(payload):
    deposit = decimal_value(payload.get("deposit_amount"), "deposit_amount")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")

    results = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        name = candidate.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"candidates[{index}].name must be a nonempty string")
        base = decimal_value(candidate.get("base_apy"), f"candidates[{index}].base_apy")
        minimum = decimal_value(candidate.get("minimum_balance", "0"), f"candidates[{index}].minimum_balance")
        checking = highest(candidate.get("checking_boosts", []), f"candidates[{index}].checking_boosts")
        card = highest(candidate.get("credit_card_bonuses", []), f"candidates[{index}].credit_card_bonuses")
        others = candidate.get("other_additive_bonuses", [])
        if not isinstance(others, list):
            raise ValueError(f"candidates[{index}].other_additive_bonuses must be a list")
        other_total = Decimal("0")
        selected_other = []
        for other_index, item in enumerate(others):
            if not isinstance(item, dict):
                raise ValueError(f"candidates[{index}].other_additive_bonuses[{other_index}] must be an object")
            apy = decimal_value(item.get("apy", "0"), "other_additive_bonuses apy")
            other_total += apy
            selected_other.append({"source": str(item.get("source", "unspecified")), "apy": clean(apy)})
        eligible = deposit >= minimum
        total = base + checking["apy"] + card["apy"] + other_total
        results.append({
            "name": name,
            "eligible_at_supplied_deposit": eligible,
            "ineligibility_reason": None if eligible else "deposit_amount is below minimum_balance",
            "minimum_balance": clean(minimum),
            "base_apy": clean(base),
            "selected_checking_boost": {"source": checking["source"], "apy": clean(checking["apy"])},
            "selected_credit_card_bonus": {"source": card["source"], "apy": clean(card["apy"])},
            "other_additive_bonuses": selected_other,
            "total_apy": clean(total),
        })
    eligible = [result for result in results if result["eligible_at_supplied_deposit"]]
    best = max(eligible, key=lambda result: Decimal(result["total_apy"])) if eligible else None
    return {"deposit_amount": clean(deposit), "results": results, "best_eligible_scenario": best}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
