#!/usr/bin/env python3
"""Rank business-account candidates from normalized JSON on stdin."""
import json
import sys
from datetime import date

OPS = {"==", "!=", ">=", ">", "<=", "<", "in"}

def compare(actual, op, expected):
    if op == "==": return actual == expected
    if op == "!=": return actual != expected
    if op == ">=": return actual >= expected
    if op == ">": return actual > expected
    if op == "<=": return actual <= expected
    if op == "<": return actual < expected
    if op == "in": return actual in expected
    raise ValueError("unsupported operator: " + str(op))

def active_priority(promotions, product_type, as_of, errors):
    choices = []
    for promotion in promotions:
        if promotion.get("product_type") != product_type:
            continue
        try:
            start = date.fromisoformat(promotion["start"])
            end = date.fromisoformat(promotion["end"])
        except (KeyError, TypeError, ValueError):
            errors.append("invalid promotion dates for " + product_type)
            continue
        if start <= as_of <= end:
            choices.append(promotion.get("priority", []))
    return choices[0] if choices else []

def evaluate(candidate, requirements):
    attrs = candidate.get("attributes", {})
    failed, unknown, confirmations = [], [], []
    for requirement in requirements:
        field, op = requirement.get("field"), requirement.get("op")
        if not field or op not in OPS:
            failed.append({"requirement": requirement, "reason": "invalid requirement"})
            continue
        if field not in attrs or attrs[field] is None:
            unknown.append(requirement)
            continue
        try:
            if not compare(attrs[field], op, requirement.get("value")):
                failed.append({"requirement": requirement, "actual": attrs[field]})
        except (TypeError, ValueError):
            failed.append({"requirement": requirement, "actual": attrs[field], "reason": "not comparable"})
    for eligibility in candidate.get("eligibility", []):
        if eligibility.get("status") != "confirmed":
            confirmations.append(eligibility)
            continue
        field, op = eligibility.get("field"), eligibility.get("op")
        if field not in attrs:
            confirmations.append(eligibility)
            continue
        try:
            if not compare(attrs[field], op, eligibility.get("value")):
                failed.append({"eligibility": eligibility, "actual": attrs[field]})
        except (TypeError, ValueError):
            failed.append({"eligibility": eligibility, "actual": attrs[field], "reason": "not comparable"})
    return failed, unknown, confirmations

def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"recommendations": {}, "errors": ["invalid JSON: " + str(exc)]}))
        return
    errors = []
    try:
        as_of = date.fromisoformat(payload["as_of"])
    except (KeyError, TypeError, ValueError):
        print(json.dumps({"recommendations": {}, "errors": ["as_of must be YYYY-MM-DD"]}))
        return
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    promotions = payload.get("promotions", [])
    if not isinstance(candidates, list):
        print(json.dumps({"recommendations": {}, "errors": ["candidates must be a list"]}))
        return

    product_types = sorted(set(requirements) | {c.get("product_type") for c in candidates if c.get("product_type")})
    output = {"recommendations": {}, "qualified": {}, "disqualified": {}, "unresolved": {}, "errors": errors}
    for product_type in product_types:
        needed = requirements.get(product_type, [])
        applicable = [c for c in candidates if c.get("product_type") == product_type]
        qualified, rejected, unresolved = [], [], []
        for candidate in applicable:
            failed, unknown, confirmations = evaluate(candidate, needed)
            name = candidate.get("name", "unnamed candidate")
            item = {"name": name, "confirmation_needed": confirmations}
            if failed:
                item["failed"] = failed
                rejected.append(item)
            elif unknown:
                item["unknown_requirements"] = unknown
                unresolved.append(item)
            else:
                qualified.append(item)
        priority = active_priority(promotions, product_type, as_of, errors)
        positions = {name: index for index, name in enumerate(priority)}
        qualified.sort(key=lambda x: (positions.get(x["name"], len(positions)), x["name"]))
        output["qualified"][product_type] = qualified
        output["disqualified"][product_type] = rejected
        output["unresolved"][product_type] = unresolved
        if qualified:
            chosen = dict(qualified[0])
            chosen["status"] = "recommended"
            chosen["promotion_applied"] = chosen["name"] in positions
            output["recommendations"][product_type] = chosen
        else:
            output["recommendations"][product_type] = {"status": "no_fully_supported_match"}
    print(json.dumps(output, sort_keys=True))

if __name__ == "__main__":
    main()
