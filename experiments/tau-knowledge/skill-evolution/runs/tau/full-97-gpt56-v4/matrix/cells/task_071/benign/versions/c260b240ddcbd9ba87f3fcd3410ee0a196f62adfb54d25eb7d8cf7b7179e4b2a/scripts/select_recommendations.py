#!/usr/bin/env python3
"""Select evidence-supported products from normalized recommendation inputs.

Reads one JSON object from stdin and writes JSON to stdout. This helper never
retrieves facts and never performs banking actions.
"""

import json
import sys
from datetime import date, datetime


OPS = {
    "==": lambda actual, expected: actual == expected,
    "!=": lambda actual, expected: actual != expected,
    ">=": lambda actual, expected: actual >= expected,
    ">": lambda actual, expected: actual > expected,
    "<=": lambda actual, expected: actual <= expected,
    "<": lambda actual, expected: actual < expected,
    "in": lambda actual, expected: actual in expected,
}


def parse_date(value):
    """Return a date from an ISO-like date or timestamp, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def requirement_matches(facts, requirement):
    if not isinstance(requirement, dict):
        return False
    field = requirement.get("field")
    operator = requirement.get("operator", "==")
    if not isinstance(field, str) or field not in facts or operator not in OPS:
        return False
    try:
        return bool(OPS[operator](facts[field], requirement.get("value")))
    except (TypeError, ValueError):
        return False


def promotion_is_active(promotion, current_time):
    if not isinstance(promotion, dict):
        return False
    current = parse_date(current_time)
    start = parse_date(promotion.get("active_from"))
    end = parse_date(promotion.get("active_to"))
    return current is not None and start is not None and end is not None and start <= current <= end


def choose(qualifying, category, promotion, active):
    if not qualifying:
        return None
    if active:
        ordered_names = promotion.get("priority", {}).get(category, [])
        if isinstance(ordered_names, list):
            by_name = {item["name"]: item for item in qualifying}
            for name in ordered_names:
                if name in by_name:
                    return by_name[name]
    # Preserve source/input order where no supported tie-breaker exists.
    return qualifying[0]


def main(payload):
    products = payload.get("products", [])
    requirements = payload.get("requirements", {})
    promotion = payload.get("promotion", {})
    current_time = payload.get("current_time")
    if not isinstance(products, list) or not isinstance(requirements, dict):
        raise ValueError("products must be a list and requirements must be an object")

    categories = list(requirements.keys())
    for product in products:
        if isinstance(product, dict) and isinstance(product.get("category"), str):
            if product["category"] not in categories:
                categories.append(product["category"])

    active = promotion_is_active(promotion, current_time)
    result = {"promotion_active": active, "categories": {}}
    for category in categories:
        needed = requirements.get(category, [])
        if not isinstance(needed, list):
            needed = []
        qualifying = []
        for product in products:
            if not isinstance(product, dict) or product.get("category") != category:
                continue
            if not isinstance(product.get("name"), str) or not isinstance(product.get("facts"), dict):
                continue
            if all(requirement_matches(product["facts"], item) for item in needed):
                qualifying.append({"name": product["name"], "facts": product["facts"]})
        selected = choose(qualifying, category, promotion, active)
        result["categories"][category] = {
            "qualifying": [item["name"] for item in qualifying],
            "selected": selected["name"] if selected else None,
        }
    return result


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
