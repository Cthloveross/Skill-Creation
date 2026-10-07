#!/usr/bin/env python3
"""Classify normalized card records against hard customer requirements.

Input is one JSON object on stdin containing customer, requirements, and candidates.
Output is one JSON object on stdout. The utility is deterministic and has no network,
account, filesystem-writing, or banking side effects.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, field, errors):
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(field + " must be numeric or null")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(field + " must be numeric or null")
        return None


def string_set(value, field, errors):
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(field + " must be a list of strings")
        return set()
    return {item.strip().casefold() for item in value if item.strip()}


def classify(candidate, customer, requirements, errors):
    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        name = "unnamed candidate"
    failures, unknown = [], []

    desired_type = requirements.get("desired_product_type")
    product_type = candidate.get("product_type")
    if desired_type is not None:
        if not isinstance(desired_type, str):
            errors.append("requirements.desired_product_type must be a string or null")
        elif not isinstance(product_type, str):
            unknown.append("product type is not documented")
        elif product_type.casefold() != desired_type.casefold():
            failures.append("product type is %s, not %s" % (product_type, desired_type))

    score = decimal(customer.get("credit_score"), "customer.credit_score", errors)
    minimum_score = decimal(candidate.get("minimum_credit_score"), name + ".minimum_credit_score", errors)
    no_score = candidate.get("minimum_credit_score_means_no_requirement", False)
    if not isinstance(no_score, bool):
        errors.append(name + ".minimum_credit_score_means_no_requirement must be boolean")
        no_score = False
    if minimum_score is None:
        unknown.append("minimum credit-score requirement is not documented")
    elif minimum_score == 0 and no_score:
        pass
    elif score is None:
        unknown.append("customer credit score was not supplied")
    elif score < minimum_score:
        failures.append("credit score %s is below documented minimum %s" % (score, minimum_score))

    held = string_set(customer.get("memberships", []), "customer.memberships", errors)
    required = string_set(candidate.get("required_memberships", []), name + ".required_memberships", errors)
    missing = sorted(required - held)
    if missing:
        failures.append("missing required membership(s): " + ", ".join(missing))

    for requirement_key, candidate_key, label in (
        ("foreign_transaction_fee_max_pct", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("minimum_payment_max_pct", "minimum_payment_percent", "minimum payment"),
    ):
        maximum = decimal(requirements.get(requirement_key), "requirements." + requirement_key, errors)
        if maximum is None:
            continue
        actual = decimal(candidate.get(candidate_key), name + "." + candidate_key, errors)
        if actual is None:
            unknown.append(label + " is not documented")
        elif actual > maximum:
            failures.append("%s %s%% exceeds %s%%" % (label, actual, maximum))

    if requirements.get("require_virtual_card_management") is True:
        virtual = candidate.get("virtual_card_management")
        if virtual is False:
            failures.append("virtual card management is not available")
        elif virtual is not True:
            unknown.append("virtual card-management availability is not documented")

    extra = candidate.get("eligibility_checks", {})
    if not isinstance(extra, dict):
        errors.append(name + ".eligibility_checks must be an object")
    else:
        for condition, state in extra.items():
            if state is False:
                failures.append("documented eligibility condition not met: " + str(condition))
            elif state is None or state == "unknown":
                unknown.append("documented eligibility condition unconfirmed: " + str(condition))
            elif state is not True:
                errors.append(name + ".eligibility check values must be true, false, or 'unknown'")

    result = {
        "name": name,
        "source_ids": candidate.get("source_ids", []),
        "reasons": failures,
        "unknown": unknown,
    }
    return ("disqualified" if failures else "uncertain" if unknown else "qualified"), result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": "invalid JSON: " + exc.msg}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return

    errors = []
    customer = payload.get("customer", {})
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
        customer = {}
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        candidates = []

    output = {"status": "ok", "qualified": [], "disqualified": [], "uncertain": [], "validation": errors}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append("candidates[%d] must be an object" % index)
            continue
        bucket, result = classify(candidate, customer, requirements, errors)
        output[bucket].append(result)
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
