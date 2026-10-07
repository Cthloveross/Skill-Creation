#!/usr/bin/env python3
"""Evaluate structured credit-card terms against explicit customer requirements.

Reads a JSON object from stdin and emits a JSON object. It performs no banking action.
"""
import json
import sys
from typing import Any, Dict, List, Tuple

CHECKS: Tuple[Tuple[str, str, str], ...] = (
    ("credit_score", "minimum_credit_score", "minimum_credit_score"),
    (
        "requires_virtual_card_management",
        "virtual_card_management",
        "virtual_card_management",
    ),
    (
        "max_foreign_transaction_fee_percent",
        "foreign_transaction_fee_percent",
        "foreign_transaction_fee_percent",
    ),
    (
        "max_minimum_payment_percent",
        "minimum_payment_percent",
        "minimum_payment_percent",
    ),
)


def evaluate_condition(preference_key: str, product_key: str, preference: Any, product: Dict[str, Any]) -> Dict[str, Any]:
    """Return a transparent pass/fail/missing result for one criterion."""
    if preference is None:
        return {"criterion": preference_key, "status": "not_requested"}
    if product_key not in product or product[product_key] is None:
        return {
            "criterion": preference_key,
            "status": "missing_product_data",
            "product_field": product_key,
        }

    actual = product[product_key]
    try:
        if preference_key == "credit_score":
            # A stated score passes when it meets or exceeds a disclosed minimum.
            passed = float(preference) >= float(actual)
            comparison = "customer_credit_score >= minimum_credit_score"
        elif preference_key == "requires_virtual_card_management":
            # Only a true requirement is restrictive; false means no requirement.
            passed = (not bool(preference)) or bool(actual)
            comparison = "virtual_card_management available when required"
        else:
            passed = float(actual) <= float(preference)
            comparison = "product_value <= customer_maximum"
    except (TypeError, ValueError):
        return {
            "criterion": preference_key,
            "status": "invalid_numeric_or_boolean_data",
            "customer_value": preference,
            "product_value": actual,
        }

    return {
        "criterion": preference_key,
        "status": "pass" if passed else "fail",
        "comparison": comparison,
        "customer_value": preference,
        "product_value": actual,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return

    if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
        print(json.dumps({"error": "products_must_be_a_list"}))
        return
    preferences = payload.get("preferences", {})
    if not isinstance(preferences, dict):
        print(json.dumps({"error": "preferences_must_be_an_object"}))
        return

    evaluations: List[Dict[str, Any]] = []
    matches: List[str] = []
    for index, product in enumerate(payload["products"]):
        if not isinstance(product, dict):
            evaluations.append({"index": index, "status": "invalid_product"})
            continue
        conditions = [
            evaluate_condition(pref_key, product_key, preferences.get(pref_key), product)
            for pref_key, product_key, _ in CHECKS
        ]
        # Unknown values for a requested criterion never qualify as a match.
        qualifies = all(c["status"] in ("pass", "not_requested") for c in conditions)
        name = product.get("name")
        product_result = {
            "index": index,
            "name": name,
            "qualifies": qualifies,
            "conditions": conditions,
            "missing_required_data": [
                c["product_field"] for c in conditions if c["status"] == "missing_product_data"
            ],
        }
        evaluations.append(product_result)
        if qualifies and isinstance(name, str) and name:
            matches.append(name)

    print(json.dumps({"evaluations": evaluations, "matches": matches}, sort_keys=True))


if __name__ == "__main__":
    main()
