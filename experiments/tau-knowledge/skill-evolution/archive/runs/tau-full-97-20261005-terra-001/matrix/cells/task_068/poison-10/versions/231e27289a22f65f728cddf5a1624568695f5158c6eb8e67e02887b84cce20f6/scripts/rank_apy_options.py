#!/usr/bin/env python3
"""Rank documented savings combinations without stacking same-category boosts."""
from decimal import Decimal, InvalidOperation
import json
import sys


def number(value, field, errors):
    try:
        value = Decimal(str(value))
        if value < 0:
            raise InvalidOperation
        return value
    except (InvalidOperation, ValueError):
        errors.append("invalid nonnegative number for " + field)
        return Decimal("0")


def main(data):
    options = data.get("options")
    if not isinstance(options, list):
        return {"ranked_options": [], "errors": ["options must be a list"]}
    ranked = []
    global_errors = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            global_errors.append("option %d must be an object" % index)
            continue
        errors = []
        base = number(option.get("base_apy"), "base_apy", errors)
        checking = [number(x, "checking_boosts", errors) for x in option.get("checking_boosts", [])]
        cards = [number(x, "card_bonuses", errors) for x in option.get("card_bonuses", [])]
        other = [number(x, "other_additive_bonuses", errors) for x in option.get("other_additive_bonuses", [])]
        requirements = option.get("requirements", {})
        if not isinstance(requirements, dict):
            errors.append("requirements must be an object")
            requirements = {}
        unmet = [key for key, met in requirements.items() if met is not True]
        best_checking = max(checking, default=Decimal("0"))
        best_card = max(cards, default=Decimal("0"))
        effective = base + best_checking + best_card + sum(other, Decimal("0"))
        ranked.append({
            "id": option.get("id", str(index)),
            "qualifies": not errors and not unmet,
            "unmet_requirements": unmet,
            "errors": errors,
            "base_apy": str(base),
            "selected_checking_boost": str(best_checking),
            "selected_card_bonus": str(best_card),
            "other_additive_bonus_total": str(sum(other, Decimal("0"))),
            "effective_apy": str(effective)
        })
    ranked.sort(key=lambda item: (item["qualifies"], Decimal(item["effective_apy"])), reverse=True)
    return {"ranked_options": ranked, "errors": global_errors,
            "method": "uses only the highest checking boost and highest card bonus per option"}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ranked_options": [], "errors": ["invalid input: " + str(exc)]}))
