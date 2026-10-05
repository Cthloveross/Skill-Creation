#!/usr/bin/env python3
"""Classify normalized card candidates against hard customer requirements.

Input JSON schema:
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
Output is JSON with qualified, disqualified, uncertain, and validation arrays.
The script is deterministic and has no external side effects.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def as_decimal(value, field, errors):
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


def as_string_set(value, field, errors):
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
    failed, unknown = [], []

    wanted_type = requirements.get("desired_product_type")
    actual_type = candidate.get("product_type")
    if wanted_type is not None:
        if not isinstance(wanted_type, str):
            errors.append("requirements.desired_product_type must be a string or null")
        elif not isinstance(actual_type, str):
            unknown.append("product type is not documented")
        elif actual_type.casefold() != wanted_type.strip().casefold():
            failed.append("product type is %s, not %s" % (actual_type, wanted_type))

    score = as_decimal(customer.get("credit_score"), "customer.credit_score", errors)
    minimum = as_decimal(candidate.get("minimum_credit_score"), name + ".minimum_credit_score", errors)
    no_score = candidate.get("minimum_credit_score_means_no_requirement")
    if no_score not in (True, False):
        errors.append(name + ".minimum_credit_score_means_no_requirement must be boolean")
        no_score = False
    if minimum is None:
        unknown.append("minimum credit-score requirement is not documented")
    elif minimum == 0 and not no_score:
        unknown.append("zero minimum score is not documented as no score requirement")
    elif minimum > 0 and score is None:
        unknown.append("customer credit score was not supplied")
    elif minimum > 0 and score < minimum:
        failed.append("credit score %s is below documented minimum %s" % (score, minimum))

    needed = as_string_set(candidate.get("required_memberships", []), name + ".required_memberships", errors)
    held = as_string_set(customer.get("memberships", []), "customer.memberships", errors)
    absent = sorted(needed - held)
    if absent:
        failed.append("missing required membership(s): " + ", ".join(absent))

    comparisons = (
        ("foreign_transaction_fee_max_pct", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("minimum_payment_max_pct", "minimum_payment_percent", "minimum payment"),
    )
    for requirement_field, candidate_field, label in comparisons:
        cap = as_decimal(requirements.get(requirement_field), "requirements." + requirement_field, errors)
        if cap is None:
            continue
        actual = as_decimal(candidate.get(candidate_field), name + "." + candidate_field, errors)
        if actual is None:
            unknown.append(label + " is not documented")
        elif actual > cap:
            failed.append("%s %s%% exceeds %s%%" % (label, actual, cap))

    wants_virtual = requirements.get("require_virtual_card_management")
    if wants_virtual not in (None, True, False):
        errors.append("requirements.require_virtual_card_management must be boolean or null")
    elif wants_virtual is True:
        available = candidate.get("virtual_card_management")
        if available is False:
            failed.append("virtual card management is not available")
        elif available is not True:
            unknown.append("virtual card-management availability is not documented")

    checks = candidate.get("eligibility_checks", {})
    if not isinstance(checks, dict):
        errors.append(name + ".eligibility_checks must be an object")
    else:
        for label, state in checks.items():
            if state is False:
                failed.append("documented eligibility condition not met: " + str(label))
            elif state is None or state == "unknown":
                unknown.append("documented eligibility condition unconfirmed: " + str(label))
            elif state is not True:
                errors.append(name + ".eligibility check values must be true, false, or 'unknown'")

    return ("disqualified" if failed else "uncertain" if unknown else "qualified"), {
        "name": name,
        "source_ids": candidate.get("source_ids", []),
        "reasons": failed,
        "unknown": unknown,
    }


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
    print(json.dumps(output, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
