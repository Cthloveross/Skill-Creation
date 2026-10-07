#!/usr/bin/env python3
"""Deterministically compare structured card facts with stated preferences.

Read JSON from stdin and write JSON to stdout. See SKILL.md for the schema.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value):
    """Return a Decimal for a supplied numeric value, or None when unknown/invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def criterion(status, observed=None, required=None, note=None):
    result = {"status": status}
    if observed is not None:
        result["observed"] = observed
    if required is not None:
        result["required"] = required
    if note:
        result["note"] = note
    return result


def compare_max(observed, maximum, label):
    if maximum is None:
        return criterion("not_requested")
    value = decimal_value(observed)
    limit = decimal_value(maximum)
    if value is None or limit is None:
        return criterion("unknown", observed=observed, required=maximum,
                         note=f"No usable published {label} was supplied.")
    status = "pass" if value <= limit else "fail"
    return criterion(status, observed=observed, required=maximum)


def compare_credit(product_minimum, customer_score):
    if customer_score is None:
        return criterion("not_requested")
    customer = decimal_value(customer_score)
    if customer is None:
        return criterion("unknown", observed=product_minimum, required=customer_score,
                         note="Customer score is not numeric.")
    # JSON null represents an explicit source statement of no minimum requirement.
    if product_minimum is None:
        return criterion("pass", observed=None, required=customer_score,
                         note="Published as having no minimum credit-score requirement.")
    minimum = decimal_value(product_minimum)
    if minimum is None:
        return criterion("unknown", observed=product_minimum, required=customer_score,
                         note="No usable published minimum credit score was supplied.")
    return criterion("pass" if customer >= minimum else "fail",
                     observed=product_minimum, required=customer_score)


def compare_virtual(observed, required):
    if required is None or required is False:
        return criterion("not_requested")
    if observed is True:
        return criterion("pass", observed=True, required=True)
    if observed is False:
        return criterion("fail", observed=False, required=True)
    return criterion("unknown", observed=observed, required=True,
                     note="Virtual-card availability was not explicitly confirmed.")


def assess_product(product, preferences):
    name = product.get("name")
    checks = {
        "credit_score": compare_credit(
            product.get("minimum_credit_score"), preferences.get("credit_score")
        ),
        "foreign_transaction_fee": compare_max(
            product.get("foreign_transaction_fee_pct"),
            preferences.get("foreign_transaction_fee_max_pct"),
            "foreign transaction fee"
        ),
        "minimum_payment": compare_max(
            product.get("minimum_payment_pct"),
            preferences.get("minimum_payment_max_pct"),
            "minimum payment percentage"
        ),
        "virtual_card_management": compare_virtual(
            product.get("virtual_card_management"),
            preferences.get("require_virtual_card_management")
        ),
    }
    basis = product.get("minimum_payment_basis")
    if preferences.get("minimum_payment_max_pct") is not None and basis is None:
        checks["minimum_payment"]["note"] = (
            "Payment percentage may pass numerically, but its published balance basis is unknown."
        )
    elif basis is not None:
        checks["minimum_payment"]["basis"] = basis

    required_checks = [check for check in checks.values() if check["status"] != "not_requested"]
    matched = bool(required_checks) and all(check["status"] == "pass" for check in required_checks)
    reasons = []
    for key, check in checks.items():
        if check["status"] in ("fail", "unknown"):
            reasons.append({"criterion": key, "status": check["status"], "note": check.get("note")})
    return {"name": name, "criteria": checks, "is_verified_match": matched, "reasons": reasons}


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"Invalid JSON input: {exc.msg}"}))
        return 2
    if not isinstance(payload, dict):
        print(json.dumps({"error": "Input must be a JSON object."}))
        return 2
    preferences = payload.get("preferences")
    products = payload.get("products")
    if not isinstance(preferences, dict) or not isinstance(products, list):
        print(json.dumps({"error": "Input requires object 'preferences' and array 'products'."}))
        return 2

    assessments = []
    for product in products:
        if not isinstance(product, dict):
            assessments.append({"name": None, "is_verified_match": False,
                                "reasons": [{"criterion": "product", "status": "unknown",
                                             "note": "Product entry is not an object."}]})
        else:
            assessments.append(assess_product(product, preferences))
    output = {
        "verified_matches": [item for item in assessments if item["is_verified_match"]],
        "non_matches": [item for item in assessments if not item["is_verified_match"]],
        "all_requirements_verified": bool(assessments) and any(
            item["is_verified_match"] for item in assessments
        ),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
