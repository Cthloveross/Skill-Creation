#!/usr/bin/env python3
"""Evidence-only selector for account recommendations.

Input: one JSON object on stdin. Output: one JSON object on stdout.
The program does not retrieve evidence and does not take banking actions.
"""
import json
import sys
from datetime import date, datetime


def parse_date(value):
    """Parse the date component of an ISO date or timestamp, else return None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def matches(actual, operator, expected):
    try:
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == ">=":
            return actual >= expected
        if operator == ">":
            return actual > expected
        if operator == "<=":
            return actual <= expected
        if operator == "<":
            return actual < expected
        if operator == "in":
            return isinstance(expected, (list, tuple, set, str, dict)) and actual in expected
    except TypeError:
        pass
    return False


def requirement_matches(facts, requirement):
    """A missing or malformed fact never satisfies a customer requirement."""
    if not isinstance(facts, dict) or not isinstance(requirement, dict):
        return False
    field = requirement.get("field")
    operator = requirement.get("operator", "==")
    if not isinstance(field, str) or field not in facts:
        return False
    return matches(facts[field], operator, requirement.get("value"))


def promotion_is_active(promotion, current_time):
    if not isinstance(promotion, dict):
        return False
    current = parse_date(current_time)
    start = parse_date(promotion.get("active_from"))
    end = parse_date(promotion.get("active_to"))
    return bool(current and start and end and start <= current <= end)


def choose(qualifying, category, promotion, active):
    """Return a supported selection, or None when a tie is not resolvable."""
    if len(qualifying) == 1:
        return qualifying[0]
    if active and isinstance(promotion, dict):
        priority = promotion.get("priority", {})
        ordered_names = priority.get(category, []) if isinstance(priority, dict) else []
        if isinstance(ordered_names, list):
            by_name = {item["name"]: item for item in qualifying}
            for name in ordered_names:
                if name in by_name:
                    return by_name[name]
    # Input order is not product evidence and is not a valid tie-breaker.
    return None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    products = payload.get("products", [])
    requirements = payload.get("requirements", {})
    if not isinstance(products, list):
        raise ValueError("products must be a list")
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")

    categories = list(requirements)
    for product in products:
        if isinstance(product, dict) and isinstance(product.get("category"), str):
            if product["category"] not in categories:
                categories.append(product["category"])

    promotion = payload.get("promotion", {})
    active = promotion_is_active(promotion, payload.get("current_time"))
    result = {"promotion_active": active, "categories": {}}
    for category in categories:
        needed = requirements.get(category, [])
        if not isinstance(needed, list):
            raise ValueError("each category's requirements must be a list")
        qualifying = []
        for product in products:
            if not isinstance(product, dict) or product.get("category") != category:
                continue
            name, facts = product.get("name"), product.get("facts")
            if not isinstance(name, str) or not name or not isinstance(facts, dict):
                continue
            if all(requirement_matches(facts, item) for item in needed):
                qualifying.append({"name": name, "facts": facts})
        selected = choose(qualifying, category, promotion, active)
        result["categories"][category] = {
            "qualifying": [item["name"] for item in qualifying],
            "selected": selected["name"] if selected else None,
            "selection_basis": (
                "sole_qualifier" if selected and len(qualifying) == 1 else
                "active_promotion_priority" if selected else
                "no_qualifier" if not qualifying else "unresolved_tie"
            ),
        }
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
