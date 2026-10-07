#!/usr/bin/env python3
"""Classify normalized credit-card records against stated hard requirements.

Reads one JSON object from stdin containing customer, requirements, and candidates.
Writes one JSON object to stdout. It has no network, account, or banking side effects.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field, errors):
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


def text_set(value, field, errors):
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

    score = number(customer.get("credit_score"), "customer.credit_score", errors)
    minimum = number(candidate.get("minimum_credit_score"), name + ".minimum_credit_score", errors)
    zero_means_none = candidate.get("minimum_credit_score_means_no_requirement", False)
    if not isinstance(zero_means_none, bool):
        errors.append(name + ".minimum_credit_score_means_no_requirement must be boolean")
        zero_means_none = False
    if minimum is None:
        unknown.append("minimum credit-score requirement is not documented")
    elif minimum == 0 and not zero_means_none:
        unknown.append("a zero minimum score is not documented as meaning no score requirement")
    elif minimum == 0:
        pass
    elif score is None:
        unknown.append("customer credit score was not supplied")
    elif score < minimum:
        failures.append("credit score %s is below documented minimum %s" % (score, minimum))

    held = text_set(customer.get("memberships", []), "customer.memberships", errors)
    required = text_set(candidate.get("required_memberships", []), name + ".required_memberships", errors)
    missing = sorted(required - held)
    if missing:
        failures.append("missing required membership(s): " + ", ".join(missing))

    comparisons = (
        ("foreign_transaction_fee_max_pct", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("minimum_payment_max_pct", "minimum_payment_percent", "minimum payment"),
    )
    for requirement_field, candidate_field, label in comparisons:
        maximum = number(requirements.get(requirement_field), "requirements." + requirement_field, errors)
        if maximum is None:
            continue
        actual = number(candidate.get(candidate_field), name + "." + candidate_field, errors)
        if actual is None:
            unknown.append(label + " is not documented")
        elif actual > maximum:
            failures.append("%s %s%% exceeds %s%%" % (label, actual, maximum))

    require_virtual = requirements.get("require_virtual_card_management")
    if require_virtual not in (None, True, False):
        errors.append("requirements.require_virtual_card_management must be boolean or null")
    elif require_virtual is True:
        available = candidate.get("virtual_card_management")
        if available is False:
            failures.append("virtual card management is not available")
        elif available is not True:
            unknown.append("virtual card-management availability is not documented")

    checks = candidate.get("eligibility_checks", {})
    if not isinstance(checks, dict):
        errors.append(name + ".eligibility_checks must be an object")
    else:
        for condition, state in checks.items():
            if state is False:
                failures.append("documented eligibility condition not met: " + str(condition))
            elif state is None or state == "unknown":
                unknown.append("documented eligibility condition unconfirmed: " + str(condition))
            elif state is not True:
                errors.append(name + ".eligibility check values must be true, false, or 'unknown'")

    record = {"name": name, "source_ids": candidate.get("source_ids", []),
              "reasons": failures, "unknown": unknown}
    return ("disqualified" if failures else "uncertain" if unknown else "qualified"), record


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
        bucket, record = classify(candidate, customer, requirements, errors)
        output[bucket].append(record)
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
