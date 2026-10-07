#!/usr/bin/env python3
"""Screen and rank product candidates against normalized requirements.

Input and output are JSON objects on stdin/stdout. This helper is deliberately
side-effect free: it never reads accounts, calls banking tools, or opens products.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


OPERATORS = {"gte", "lte", "eq", "true", "false", "exists"}


def emit(payload):
    sys.stdout.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def as_number(value):
    if isinstance(value, bool) or value is None:
        raise InvalidOperation
    return Decimal(str(value))


def parse_date(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO YYYY-MM-DD string") from exc


def validate_input(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    candidates = data.get("candidates")
    requirements = data.get("requirements")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")
    if not isinstance(requirements, list):
        raise ValueError("requirements must be a list")

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        if not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            raise ValueError(f"candidates[{index}].name must be a nonempty string")
        if not isinstance(candidate.get("attributes"), dict):
            raise ValueError(f"candidates[{index}].attributes must be an object")

    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError(f"requirements[{index}] must be an object")
        if not isinstance(requirement.get("key"), str) or not requirement["key"].strip():
            raise ValueError(f"requirements[{index}].key must be a nonempty string")
        operator = requirement.get("operator")
        if operator not in OPERATORS:
            raise ValueError(f"requirements[{index}].operator is unsupported")
        if operator in {"gte", "lte", "eq"} and "value" not in requirement:
            raise ValueError(f"requirements[{index}].value is required for {operator}")


def evaluate(attribute_present, actual, requirement):
    key = requirement["key"]
    operator = requirement["operator"]
    if operator == "exists":
        if attribute_present and actual is not None:
            return None
        return {"key": key, "status": "unknown", "reason": "required attribute is missing"}
    if not attribute_present or actual is None:
        return {"key": key, "status": "unknown", "reason": "required attribute is missing"}

    if operator == "true":
        if actual is True:
            return None
        return {"key": key, "status": "failed", "reason": "must be true"}
    if operator == "false":
        if actual is False:
            return None
        return {"key": key, "status": "failed", "reason": "must be false"}

    expected = requirement["value"]
    if operator == "eq":
        if actual == expected:
            return None
        return {"key": key, "status": "failed", "reason": "does not equal required value"}

    try:
        actual_number = as_number(actual)
        expected_number = as_number(expected)
    except (InvalidOperation, ValueError):
        return {
            "key": key,
            "status": "unknown",
            "reason": "numeric comparison requires numeric candidate and requirement values",
        }

    passes = actual_number >= expected_number if operator == "gte" else actual_number <= expected_number
    if passes:
        return None
    relation = "at least" if operator == "gte" else "at most"
    return {"key": key, "status": "failed", "reason": f"must be {relation} the required value"}


def promotion_is_active(data):
    promotion = data.get("promotion")
    if promotion is None:
        return False, []
    if not isinstance(promotion, dict):
        raise ValueError("promotion must be an object when supplied")
    priority = promotion.get("priority_order")
    if not isinstance(priority, list) or not all(isinstance(item, str) for item in priority):
        raise ValueError("promotion.priority_order must be a list of strings")
    if "as_of_date" not in data:
        return False, priority
    current = parse_date(data["as_of_date"], "as_of_date")
    start = parse_date(promotion.get("active_from"), "promotion.active_from")
    end = parse_date(promotion.get("active_through"), "promotion.active_through")
    if end < start:
        raise ValueError("promotion.active_through cannot be earlier than active_from")
    return start <= current <= end, priority


def main():
    try:
        data = json.load(sys.stdin)
        validate_input(data)
        active, priority = promotion_is_active(data)

        qualifying = []
        rejected = []
        for position, candidate in enumerate(data["candidates"]):
            failures = []
            attributes = candidate["attributes"]
            for requirement in data["requirements"]:
                key = requirement["key"]
                result = evaluate(key in attributes, attributes.get(key), requirement)
                if result is not None:
                    failures.append(result)
            if failures:
                rejected.append({"name": candidate["name"], "failures": failures})
            else:
                record = {
                    "name": candidate["name"],
                    "product_type": candidate.get("product_type"),
                    "attributes": attributes,
                    "_source_position": position,
                }
                qualifying.append(record)

        priority_index = {name: index for index, name in enumerate(priority)}
        if active:
            qualifying.sort(key=lambda item: (priority_index.get(item["name"], len(priority)), item["_source_position"]))
        for record in qualifying:
            record.pop("_source_position", None)

        emit({
            "ok": True,
            "promotion_active": active,
            "qualifying": qualifying,
            "rejected": rejected,
        })
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        emit({"ok": False, "error": str(exc)})


if __name__ == "__main__":
    main()
