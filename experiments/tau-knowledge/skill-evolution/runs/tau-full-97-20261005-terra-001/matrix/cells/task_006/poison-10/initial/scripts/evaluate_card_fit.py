#!/usr/bin/env python3
"""Compare normalized card facts with explicit customer requirements.

Input and output are JSON objects on stdin/stdout. See SKILL.md for schema.
"""
import json
import sys

PRODUCT_FIELDS = {
    "foreign_transaction_fee_percent": "max_foreign_transaction_fee_percent",
    "minimum_payment_percent": "max_minimum_payment_percent",
}


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"fit": None, "checks": {}, "missing_product_fields": [],
                          "reasons": ["Input must be a JSON object: " + str(exc)]}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"fit": None, "checks": {}, "missing_product_fields": [],
                          "reasons": ["Input must be a JSON object."]}))
        return

    product = data.get("product", {})
    requirements = data.get("requirements", {})
    if not isinstance(product, dict) or not isinstance(requirements, dict):
        print(json.dumps({"fit": None, "checks": {}, "missing_product_fields": [],
                          "reasons": ["product and requirements must be JSON objects."]}))
        return

    checks = {}
    missing = []
    reasons = []

    for product_key, requirement_key in PRODUCT_FIELDS.items():
        if requirement_key not in requirements:
            continue
        maximum = requirements[requirement_key]
        if not is_number(maximum):
            checks[product_key] = {"status": "invalid_requirement"}
            reasons.append(requirement_key + " must be a non-negative number.")
            continue
        value = product.get(product_key)
        if not is_number(value):
            checks[product_key] = {"status": "unknown", "maximum": maximum}
            missing.append(product_key)
            reasons.append("The product " + product_key + " is not available as a non-negative number.")
            continue
        passed = value <= maximum
        checks[product_key] = {
            "status": "pass" if passed else "fail",
            "product_value": value,
            "maximum": maximum,
        }
        if not passed:
            reasons.append(product_key + " exceeds the customer's maximum.")

    virtual_requirement = requirements.get("requires_virtual_card_management")
    if virtual_requirement is not None:
        if not isinstance(virtual_requirement, bool):
            checks["virtual_card_management"] = {"status": "invalid_requirement"}
            reasons.append("requires_virtual_card_management must be true or false.")
        elif virtual_requirement:
            available = product.get("virtual_card_management")
            if not isinstance(available, bool):
                checks["virtual_card_management"] = {"status": "unknown", "required": True}
                missing.append("virtual_card_management")
                reasons.append("Virtual card management availability is not confirmed.")
            else:
                checks["virtual_card_management"] = {
                    "status": "pass" if available else "fail",
                    "product_value": available,
                    "required": True,
                }
                if not available:
                    reasons.append("The product does not provide required virtual card management.")

    statuses = [check["status"] for check in checks.values()]
    if not checks:
        fit = None
        reasons.append("No supported comparison requirements were supplied.")
    elif any(status in ("unknown", "invalid_requirement") for status in statuses):
        fit = None
    else:
        fit = all(status == "pass" for status in statuses)
        if fit:
            reasons.append("All supplied requirements pass.")

    print(json.dumps({
        "fit": fit,
        "checks": checks,
        "missing_product_fields": missing,
        "reasons": reasons,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
