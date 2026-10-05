#!/usr/bin/env python3
"""Rank documented account products against explicit customer requirements.

Input and output are JSON objects on stdin/stdout. This utility is read-only.
"""
import json
import sys
from datetime import date


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    return date.fromisoformat(value)


def feature_failure(features, key, expected, mode):
    if key not in features:
        return {"feature": key, "reason": "missing_documented_fact"}
    actual = features[key]
    if mode == "minimum":
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return {"feature": key, "reason": "non_numeric_documented_value", "actual": actual}
        if actual < expected:
            return {"feature": key, "reason": "below_required_minimum", "required": expected, "actual": actual}
    elif actual != expected:
        return {"feature": key, "reason": "does_not_equal_required_value", "required": expected, "actual": actual}
    return None


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


def main(payload):
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
        matches, rejected = [], []
        for product in products:
            if not isinstance(product, dict) or product.get("product_type") != product_type:
                continue
            name = product.get("name")
            features = product.get("features")
            if not isinstance(name, str) or not isinstance(features, dict):
                rejected.append({"name": name if isinstance(name, str) else "<unnamed>",
                                 "failures": [{"reason": "invalid_product_record"}]})
                continue
            failures = []
            for key, expected in minimums.items():
                failure = feature_failure(features, key, expected, "minimum")
                if failure:
                    failures.append(failure)
            for key, expected in equals.items():
                failure = feature_failure(features, key, expected, "equals")
                if failure:
                    failures.append(failure)
            if failures:
                rejected.append({"name": name, "failures": failures})
            else:
                matches.append({"name": name, "features": features,
                                "promotion_rank": priority_index.get(name)})

        matches.sort(key=lambda item: (item["promotion_rank"] is None,
                                       item["promotion_rank"] if item["promotion_rank"] is not None else 0,
                                       item["name"]))
        for item in matches:
            item.pop("promotion_rank", None)
        result["recommendations"][product_type] = {
            "status": "confirmed_match" if matches else "no_confirmed_match",
            "active_promotion_priority": priority,
            "ranked_matches": matches,
            "rejected_products": rejected,
        }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
