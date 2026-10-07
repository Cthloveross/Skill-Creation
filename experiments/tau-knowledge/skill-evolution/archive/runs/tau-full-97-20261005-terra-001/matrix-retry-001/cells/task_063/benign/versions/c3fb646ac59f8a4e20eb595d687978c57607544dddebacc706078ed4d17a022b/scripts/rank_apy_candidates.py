#!/usr/bin/env python3
"""Rank APY candidates while enforcing non-stacking card/checking bonuses.

JSON input: {"balance": "8000", "candidates": [{"name": "...",
"base_apy": 3.0, "card_bonuses": [0.15], "checking_boosts": [],
"additive_bonuses": [0.025]}]}.  JSON output contains sorted results.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("%s must be numeric" % field)
    if result < 0:
        raise ValueError("%s cannot be negative" % field)
    return result


def component_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("%s must be an array" % field)
    return [number(x, field) for x in value]


def main(payload):
    balance = number(payload.get("balance"), "balance")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array")
    results = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str):
            raise ValueError("each candidate needs a string name")
        base = number(candidate.get("base_apy"), "base_apy")
        cards = component_list(candidate.get("card_bonuses", []), "card_bonuses")
        checking = component_list(candidate.get("checking_boosts", []), "checking_boosts")
        additive = component_list(candidate.get("additive_bonuses", []), "additive_bonuses")
        card_selected = max(cards) if cards else Decimal("0")
        checking_selected = max(checking) if checking else Decimal("0")
        effective = base + card_selected + checking_selected + sum(additive, Decimal("0"))
        estimate = balance * effective / Decimal("100")
        results.append({
            "name": candidate["name"],
            "base_apy": str(base),
            "selected_highest_card_bonus": str(card_selected),
            "selected_highest_checking_boost": str(checking_selected),
            "additive_bonus_total": str(sum(additive, Decimal("0"))),
            "effective_apy": str(effective),
            "constant_balance_one_year_interest_estimate": str(estimate.quantize(Decimal("0.01")))
        })
    results.sort(key=lambda item: Decimal(item["effective_apy"]), reverse=True)
    return {"ok": True, "balance": str(balance), "ranking": results,
            "note": "Card bonuses and checking boosts are each reduced to their single highest supplied value."}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw)))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
