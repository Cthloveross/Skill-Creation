#!/usr/bin/env python3
"""Rank documented banking products from JSON supplied on stdin.

The program is deliberately catalog-agnostic: the caller supplies current product
facts, customer facts, requirements, and time-bounded promotional priorities.
It performs no I/O other than JSON stdin/stdout and no banking action.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation

MISSING = object()
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
OPERATORS = {"gte", "lte", "equals", "is_true", "exists"}


def error(message):
    sys.stdout.write(json.dumps({"ok": False, "error": message}, separators=(",", ":")) + "\n")


def date_part(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " must be a string containing YYYY-MM-DD")
    match = DATE_RE.search(value)
    if not match:
        raise ValueError(label + " must contain YYYY-MM-DD")
    # Lexical comparison is safe for zero-padded ISO dates after format validation.
    year, month, day = (int(part) for part in match.group(1).split("-"))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        raise ValueError(label + " contains an invalid date")
    return match.group(1)


def numeric(value):
    if isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value))


def compare(actual, operator, expected):
    if operator == "exists":
        return actual is not MISSING and actual is not None
    if actual is MISSING or actual is None:
        return False
    if operator == "is_true":
        return actual is True
    if operator == "equals":
        # Treat numeric JSON values consistently (for example 0 and 0.00).
        try:
            return numeric(actual) == numeric(expected)
        except (InvalidOperation, ValueError):
            return actual == expected
    if operator in ("gte", "lte"):
        try:
            left, right = numeric(actual), numeric(expected)
        except (InvalidOperation, ValueError):
            return False
        return left >= right if operator == "gte" else left <= right
    raise ValueError("unsupported operator: " + str(operator))


def rule_reason(rule, actual):
    field = rule["field"]
    if actual is MISSING or actual is None:
        return "missing evidence for " + field
    operator = rule["operator"]
    if operator == "is_true":
        return field + " is not confirmed true"
    if operator == "exists":
        return "missing evidence for " + field
    return field + " does not satisfy " + operator + " " + str(rule.get("value"))


def validate_rule(rule, context):
    if not isinstance(rule, dict):
        raise ValueError(context + " rule must be an object")
    field = rule.get("field")
    operator = rule.get("operator")
    if not isinstance(field, str) or not field:
        raise ValueError(context + " rule field must be a nonempty string")
    if operator not in OPERATORS:
        raise ValueError(context + " rule has unsupported operator")
    if operator not in ("is_true", "exists") and "value" not in rule:
        raise ValueError(context + " rule requires value")


def evaluate_rules(rules, values, context):
    reasons = []
    for rule in rules:
        validate_rule(rule, context)
        actual = values.get(rule["field"], MISSING)
        if not compare(actual, rule["operator"], rule.get("value")):
            reasons.append(rule_reason(rule, actual))
    return reasons


def active_ranks(promotions, as_of):
    ranks = {}
    for index, promotion in enumerate(promotions):
        if not isinstance(promotion, dict):
            raise ValueError("promotion must be an object")
        name = promotion.get("name")
        rank = promotion.get("rank", index + 1)
        if not isinstance(name, str) or not name:
            raise ValueError("promotion name must be a nonempty string")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            raise ValueError("promotion rank must be a positive integer")
        start = date_part(promotion.get("start"), "promotion start")
        end = date_part(promotion.get("end"), "promotion end")
        if start > end:
            raise ValueError("promotion start is after promotion end")
        if start <= as_of <= end:
            ranks[name] = min(rank, ranks.get(name, rank))
    return ranks


def evaluate_category(category_name, spec, as_of):
    if not isinstance(spec, dict):
        raise ValueError("category " + category_name + " must be an object")
    facts = spec.get("customer_facts", {})
    requirements = spec.get("requirements", [])
    products = spec.get("products", [])
    promotions = spec.get("promotions", [])
    if not isinstance(facts, dict) or not isinstance(requirements, list):
        raise ValueError("category " + category_name + " has invalid facts or requirements")
    if not isinstance(products, list) or not isinstance(promotions, list):
        raise ValueError("category " + category_name + " has invalid products or promotions")

    ranks = active_ranks(promotions, as_of)
    qualifying = []
    not_qualified = []
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError("product must be an object")
        name = product.get("name")
        attributes = product.get("attributes", {})
        eligibility = product.get("eligibility", [])
        if not isinstance(name, str) or not name:
            raise ValueError("product name must be a nonempty string")
        if not isinstance(attributes, dict) or not isinstance(eligibility, list):
            raise ValueError("product " + name + " has invalid attributes or eligibility")
        reasons = evaluate_rules(requirements, attributes, "requirement")
        reasons.extend(evaluate_rules(eligibility, facts, "eligibility"))
        if reasons:
            not_qualified.append({"name": name, "reasons": reasons})
        else:
            qualifying.append({"name": name, "promotion_rank": ranks.get(name), "_index": index})

    qualifying.sort(key=lambda item: (item["promotion_rank"] is None,
                                      item["promotion_rank"] if item["promotion_rank"] is not None else 0,
                                      item["_index"]))
    promotion_applied = bool(qualifying and any(item["promotion_rank"] is not None for item in qualifying))
    public_qualifying = [
        {"name": item["name"], "promotion_rank": item["promotion_rank"]}
        for item in qualifying
    ]
    return {
        "recommendation": qualifying[0]["name"] if qualifying else None,
        "qualifying_products": public_qualifying,
        "not_qualified": not_qualified,
        "promotion_applied": promotion_applied,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        as_of = date_part(payload.get("as_of"), "as_of")
        categories = payload.get("categories")
        if not isinstance(categories, dict) or not categories:
            raise ValueError("categories must be a nonempty object")
        results = {name: evaluate_category(name, spec, as_of) for name, spec in categories.items()}
        sys.stdout.write(json.dumps({"ok": True, "as_of": as_of, "categories": results}, separators=(",", ":")) + "\n")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        error(str(exc))


if __name__ == "__main__":
    main()
