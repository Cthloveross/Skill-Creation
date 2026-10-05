#!/usr/bin/env python3
"""Classify normalized card candidates against hard customer requirements.

Input JSON:
{
  "customer": {"credit_score": number|null, "memberships": [string]},
  "requirements": {
    "desired_product_type": string|null,
    "foreign_transaction_fee_max_pct": number|null,
    "minimum_payment_max_pct": number|null,
    "require_virtual_card_management": boolean|null
  },
  "candidates": [normalized candidate objects]
}

Output JSON contains qualified, disqualified, uncertain, and validation arrays.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, label, errors):
    """Return Decimal value or None, recording invalid supplied numeric values."""
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(label + " must be numeric or null")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(label + " must be numeric or null")
        return None


def string_set(value, label, errors):
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(label + " must be a list of strings")
        return set()
    return {item.strip().casefold() for item in value if item.strip()}


def classify(candidate, customer, requirements, errors):
    """Return bucket name and a concise result for one normalized candidate."""
    name = candidate.get("name") if isinstance(candidate.get("name"), str) else "unnamed candidate"
    failures = []
    unknown = []

    wanted_type = requirements.get("desired_product_type")
    actual_type = candidate.get("product_type")
    if wanted_type is not None:
        if not isinstance(wanted_type, str):
            errors.append("requirements.desired_product_type must be a string or null")
        elif not isinstance(actual_type, str):
            unknown.append("product type is not documented")
        elif actual_type.casefold() != wanted_type.strip().casefold():
            failures.append("product type is %s, not %s" % (actual_type, wanted_type))

    customer_score = number(customer.get("credit_score"), "customer.credit_score", errors)
    minimum_score = number(candidate.get("minimum_credit_score"), name + ".minimum_credit_score", errors)
    zero_means_none = candidate.get("minimum_credit_score_means_no_requirement")
    if zero_means_none not in (True, False):
        errors.append(name + ".minimum_credit_score_means_no_requirement must be boolean")
        zero_means_none = False
    if minimum_score is None:
        unknown.append("minimum credit-score requirement is not documented")
    elif minimum_score == 0 and not zero_means_none:
        unknown.append("zero score is not documented as no score requirement")
    elif minimum_score > 0 and customer_score is None:
        unknown.append("customer credit score was not supplied")
    elif minimum_score > 0 and customer_score < minimum_score:
        failures.append("credit score %s is below documented minimum %s" % (customer_score, minimum_score))

    required_memberships = string_set(
        candidate.get("required_memberships", []), name + ".required_memberships", errors
    )
    held_memberships = string_set(customer.get("memberships", []), "customer.memberships", errors)
    missing_memberships = sorted(required_memberships - held_memberships)
    if missing_memberships:
        failures.append("missing required membership(s): " + ", ".join(missing_memberships))

    for requirement_field, candidate_field, label in (
        ("foreign_transaction_fee_max_pct", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("minimum_payment_max_pct", "minimum_payment_percent", "minimum payment"),
    ):
        cap = number(requirements.get(requirement_field), "requirements." + requirement_field, errors)
        if cap is None:
            continue
        actual = number(candidate.get(candidate_field), name + "." + candidate_field, errors)
        if actual is None:
            unknown.append(label + " is not documented")
        elif actual > cap:
            failures.append("%s %s%% exceeds %s%%" % (label, actual, cap))

    virtual_required = requirements.get("require_virtual_card_management")
    if virtual_required not in (None, True, False):
        errors.append("requirements.require_virtual_card_management must be boolean or null")
    elif virtual_required is True:
        availability = candidate.get("virtual_card_management")
        if availability is False:
            failures.append("virtual card management is not available")
        elif availability is not True:
            unknown.append("virtual card-management availability is not documented")

    checks = candidate.get("eligibility_checks", {})
    if not isinstance(checks, dict):
        errors.append(name + ".eligibility_checks must be an object")
    else:
        for label, state in checks.items():
            if state is False:
                failures.append("documented eligibility condition not met: " + str(label))
            elif state is None or state == "unknown":
                unknown.append("documented eligibility condition unconfirmed: " + str(label))
            elif state is not True:
                errors.append(name + ".eligibility check values must be true, false, or 'unknown'")

    result = {
        "name": name,
        "source_ids": candidate.get("source_ids", []),
        "reasons": failures,
        "unknown": unknown,
    }
    if failures:
        return "disqualified", result
    if unknown:
        return "uncertain", result
    return "qualified", result


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": "invalid JSON: " + exc.msg}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return

    errors = []
    customer = data.get("customer", {})
    requirements = data.get("requirements", {})
    candidates = data.get("candidates", [])
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
        customer = {}
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        candidates = []

    output = {
        "status": "ok",
        "qualified": [],
        "disqualified": [],
        "uncertain": [],
        "validation": errors,
    }
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append("candidates[%d] must be an object" % index)
            continue
        bucket, result = classify(candidate, customer, requirements, errors)
        output[bucket].append(result)
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
