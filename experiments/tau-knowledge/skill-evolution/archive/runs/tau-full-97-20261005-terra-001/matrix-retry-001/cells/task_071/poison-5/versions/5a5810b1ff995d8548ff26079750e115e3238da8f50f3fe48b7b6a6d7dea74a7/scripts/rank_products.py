#!/usr/bin/env python3
"""Classify and rank documented account products against explicit requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. The utility is
read-only and does not retrieve records, make recommendations to a customer, or perform
banking actions.
"""
import json
import sys
from datetime import date


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    return date.fromisoformat(value)


def requirement_result(features, key, expected, mode):
    if key not in features:
        return {"feature": key, "state": "missing_documented_fact"}
    actual = features[key]
    if mode == "minimum":
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return {"feature": key, "state": "not_met", "reason": "non_numeric_documented_value", "actual": actual}
        if actual < expected:
            return {"feature": key, "state": "not_met", "reason": "below_required_minimum", "required": expected, "actual": actual}
    elif actual != expected:
        return {"feature": key, "state": "not_met", "reason": "does_not_equal_required_value", "required": expected, "actual": actual}
    return {"feature": key, "state": "met", "actual": actual}


def active_priority(promotions, product_type, as_of):
    ordered = []
    for promotion in promotions:
        if not isinstance(promotion, dict) or promotion.get("product_type") != product_type:
            continue
        try:
            start = parse_date(promotion.get("start"), "promotion.start")
            end = parse_date(promotion.get("end"), "promotion.end")
        except ValueError:
            continue
        if start <= as_of <= end:
            for name in promotion.get("priority", []):
                if isinstance(name, str) and name not in ordered:
                    ordered.append(name)
    return ordered


def ranked(items):
    return sorted(items, key=lambda item: (
        item["promotion_rank"] is None,
        item["promotion_rank"] if item["promotion_rank"] is not None else 0,
        item["name"],
    ))


def public_item(product, assessments, promotion_rank):
    return {
        "name": product["name"],
        "features": product["features"],
        "requirement_assessments": assessments,
        "promotion_rank": promotion_rank,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(payload["as_of"], "as_of")
    requirements = payload.get("requirements", {})
    products = payload.get("products", [])
    promotions = payload.get("promotions", [])
    if not isinstance(requirements, dict) or not isinstance(products, list) or not isinstance(promotions, list):
        raise ValueError("requirements must be an object; products and promotions must be arrays")

    result = {"as_of": as_of.isoformat(), "recommendations": {}}
    for product_type, constraints in requirements.items():
        if not isinstance(constraints, dict):
            raise ValueError(f"requirements.{product_type} must be an object")
        minimums = constraints.get("minimums", {})
        equals = constraints.get("equals", {})
        if not isinstance(minimums, dict) or not isinstance(equals, dict):
            raise ValueError(f"requirements.{product_type}.minimums and equals must be objects")
        for key, value in minimums.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"minimum requirement {product_type}.{key} must be numeric")

        priority = active_priority(promotions, product_type, as_of)
        priority_index = {name: index for index, name in enumerate(priority)}
        confirmed, conditional, rejected = [], [], []

        for product in products:
            if not isinstance(product, dict) or product.get("product_type") != product_type:
                continue
            name, features = product.get("name"), product.get("features")
            if not isinstance(name, str) or not isinstance(features, dict):
                rejected.append({"name": name if isinstance(name, str) else "<unnamed>", "failures": [{"reason": "invalid_product_record"}]})
                continue

            assessments = []
            for key, expected in minimums.items():
                assessments.append(requirement_result(features, key, expected, "minimum"))
            for key, expected in equals.items():
                assessments.append(requirement_result(features, key, expected, "equals"))
            item = public_item(product, assessments, priority_index.get(name))
            failures = [a for a in assessments if a["state"] == "not_met"]
            missing = [a for a in assessments if a["state"] == "missing_documented_fact"]
            if failures:
                rejected.append({"name": name, "features": features, "failures": failures, "missing": missing})
            elif missing:
                conditional.append(item)
            else:
                confirmed.append(item)

        confirmed, conditional = ranked(confirmed), ranked(conditional)
        for collection in (confirmed, conditional):
            for item in collection:
                item.pop("promotion_rank", None)
        status = "confirmed_match" if confirmed else ("conditional_candidate" if conditional else "no_candidate")
        result["recommendations"][product_type] = {
            "status": status,
            "active_promotion_priority": priority,
            "ranked_confirmed_matches": confirmed,
            "ranked_conditional_candidates": conditional,
            "rejected_products": rejected,
        }
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
