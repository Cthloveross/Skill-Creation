#!/usr/bin/env python3
"""Screen structured card offers against stated requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. The script makes no account, application, or banking-tool calls.
"""
import json
import sys


def number(value, field, card_name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{card_name}.{field} must be a number")
    return value


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    requirements = data.get("requirements")
    cards = data.get("cards")
    if not isinstance(requirements, dict) or not isinstance(cards, list):
        raise ValueError("requirements must be an object and cards must be an array")

    category = requirements.get("main_category", "")
    if not isinstance(category, str):
        raise ValueError("requirements.main_category must be a string")
    need_zero_foreign = requirements.get("no_foreign_transaction_fee", False)
    need_protection = requirements.get("purchase_protection", False)
    minimum_limit = requirements.get("minimum_possible_limit", 0)
    if isinstance(minimum_limit, bool) or not isinstance(minimum_limit, (int, float)):
        raise ValueError("requirements.minimum_possible_limit must be a number")

    matches, nonmatches = [], []
    for card in cards:
        if not isinstance(card, dict) or not isinstance(card.get("name"), str):
            raise ValueError("each card must have a string name")
        name = card["name"]
        max_limit = number(card.get("max_limit"), "max_limit", name)
        foreign_fee = number(card.get("foreign_transaction_fee"), "foreign_transaction_fee", name)
        base_rate = number(card.get("base_rate", 0), "base_rate", name)
        rates = card.get("category_rates", {})
        if not isinstance(rates, dict):
            raise ValueError(f"{name}.category_rates must be an object")
        category_rate = number(rates.get(category, base_rate), f"category_rates.{category}", name)
        protection = card.get("purchase_protection", False)
        if not isinstance(protection, bool):
            raise ValueError(f"{name}.purchase_protection must be boolean")

        failures = []
        if need_zero_foreign and foreign_fee != 0:
            failures.append("foreign_transaction_fee_not_zero")
        if need_protection and not protection:
            failures.append("no_purchase_protection")
        if max_limit < minimum_limit:
            failures.append("maximum_limit_below_requested_capacity")

        result = {
            "name": name,
            "max_limit": max_limit,
            "foreign_transaction_fee": foreign_fee,
            "foreign_fee_condition": card.get("foreign_fee_condition", ""),
            "purchase_protection": protection,
            "main_category_rate": category_rate,
            "base_rate": base_rate,
            "requirements": card.get("requirements", []),
        }
        if failures:
            result["unmet_requirements"] = failures
            nonmatches.append(result)
        else:
            matches.append(result)

    matches.sort(key=lambda x: (-x["main_category_rate"], -x["base_rate"], -x["max_limit"], x["name"]))
    nonmatches.sort(key=lambda x: (len(x["unmet_requirements"]), x["name"]))
    return {"hard_matches": matches, "nonmatches": nonmatches}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
