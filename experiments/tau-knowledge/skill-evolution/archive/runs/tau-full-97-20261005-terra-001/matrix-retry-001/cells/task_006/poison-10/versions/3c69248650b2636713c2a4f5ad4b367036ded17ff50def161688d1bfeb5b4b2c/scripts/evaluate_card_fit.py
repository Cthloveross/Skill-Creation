#!/usr/bin/env python3
"""Classify documented card candidates against hard customer requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs
no network, filesystem, account, or banking operation.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value, path, errors):
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{path} must be a number or null")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{path} must be a number or null")
        return None


def date_value(value, path, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{path} must be YYYY-MM-DD or null")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{path} must be YYYY-MM-DD or null")
        return None


def string_set(value, path, errors):
    if value is None:
        return set()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{path} must be a list of strings")
        return set()
    return {item.strip().casefold() for item in value}


def candidate_name(candidate):
    name = candidate.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else "unnamed candidate"


def classify(candidate, customer, requirements, errors):
    label = candidate_name(candidate)
    reasons, unknown = [], []

    desired_type = requirements.get("desired_product_type")
    product_type = candidate.get("product_type")
    if desired_type is not None:
        if not isinstance(desired_type, str):
            errors.append("requirements.desired_product_type must be a string or null")
        elif product_type is None:
            unknown.append("product type is not documented")
        elif not isinstance(product_type, str):
            errors.append(f"candidate {label}: product_type must be a string or null")
        elif product_type.casefold() != desired_type.casefold():
            reasons.append(f"product type is {product_type}, not {desired_type}")

    score = number(customer.get("credit_score"), "customer.credit_score", errors)
    minimum_score = number(candidate.get("minimum_credit_score"),
                           f"candidate {label}: minimum_credit_score", errors)
    no_score = candidate.get("minimum_credit_score_means_no_requirement", False)
    if not isinstance(no_score, bool):
        errors.append(f"candidate {label}: minimum_credit_score_means_no_requirement must be boolean")
        no_score = False
    if minimum_score is None:
        unknown.append("minimum credit-score requirement is not documented")
    elif minimum_score == 0 and no_score:
        pass
    elif score is None:
        unknown.append("customer credit score was not supplied")
    elif score < minimum_score:
        reasons.append(f"credit score {score} is below documented minimum {minimum_score}")

    memberships = string_set(customer.get("memberships", []), "customer.memberships", errors)
    required = string_set(candidate.get("required_memberships", []),
                          f"candidate {label}: required_memberships", errors)
    absent = sorted(required - memberships)
    if absent:
        reasons.append("missing required membership(s): " + ", ".join(absent))

    fee_limit = number(requirements.get("foreign_transaction_fee_max_pct"),
                       "requirements.foreign_transaction_fee_max_pct", errors)
    if fee_limit is not None:
        fee = number(candidate.get("foreign_transaction_fee_percent"),
                     f"candidate {label}: foreign_transaction_fee_percent", errors)
        if fee is None:
            unknown.append("foreign transaction fee is not documented")
        elif fee > fee_limit:
            reasons.append(f"foreign transaction fee {fee}% exceeds {fee_limit}%")

    payment_limit = number(requirements.get("minimum_payment_max_pct"),
                           "requirements.minimum_payment_max_pct", errors)
    if payment_limit is not None:
        payment = number(candidate.get("minimum_payment_percent"),
                         f"candidate {label}: minimum_payment_percent", errors)
        if payment is None:
            unknown.append("minimum-payment percentage is not documented")
        elif payment > payment_limit:
            reasons.append(f"minimum payment {payment}% exceeds {payment_limit}%")
        basis = candidate.get("minimum_payment_basis")
        if basis is not None and not isinstance(basis, str):
            errors.append(f"candidate {label}: minimum_payment_basis must be a string or null")

    if requirements.get("require_virtual_card_management") is True:
        virtual = candidate.get("virtual_card_management")
        if virtual is False:
            reasons.append("virtual card management is not available")
        elif virtual is not True:
            unknown.append("virtual card-management availability is not documented")

    as_of = date_value(requirements.get("as_of"), "requirements.as_of", errors)
    starts = date_value(candidate.get("available_from"), f"candidate {label}: available_from", errors)
    ends = date_value(candidate.get("available_through"), f"candidate {label}: available_through", errors)
    if starts is not None or ends is not None:
        if as_of is None:
            unknown.append("date is needed to assess offer window")
        elif starts is not None and as_of < starts:
            reasons.append("offer is not active on supplied date")
        elif ends is not None and as_of > ends:
            reasons.append("offer expired before supplied date")

    checks = candidate.get("eligibility_checks", {})
    if not isinstance(checks, dict):
        errors.append(f"candidate {label}: eligibility_checks must be an object")
    else:
        for condition, state in checks.items():
            if state is False:
                reasons.append(f"documented eligibility condition not met: {condition}")
            elif state is None or state == "unknown":
                unknown.append(f"documented eligibility condition unconfirmed: {condition}")
            elif state is not True:
                errors.append(f"candidate {label}: eligibility check {condition!r} must be true, false, or 'unknown'")

    return ("disqualified" if reasons else "uncertain" if unknown else "qualified", {
        "name": label,
        "source_ids": candidate.get("source_ids", []),
        "reasons": reasons,
        "unknown": unknown,
    })


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": f"invalid JSON: {exc.msg}"}))
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
            errors.append(f"candidates[{index}] must be an object")
            continue
        bucket, result = classify(candidate, customer, requirements, errors)
        output[bucket].append(result)
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
