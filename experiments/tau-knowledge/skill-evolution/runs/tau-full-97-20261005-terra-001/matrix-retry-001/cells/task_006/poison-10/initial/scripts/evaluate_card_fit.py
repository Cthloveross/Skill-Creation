#!/usr/bin/env python3
"""Deterministically classify documented card candidates against hard constraints.

Reads one JSON object from stdin and writes one JSON object to stdout.  It performs
no network, filesystem, account, or banking operations.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def decimal_or_none(value, path, validation):
    if value is None:
        return None
    if isinstance(value, bool):
        validation.append(f"{path} must be a number or null")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        validation.append(f"{path} must be a number or null")
        return None


def parse_date(value, path, validation):
    if value is None:
        return None
    if not isinstance(value, str):
        validation.append(f"{path} must be YYYY-MM-DD or null")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        validation.append(f"{path} must be YYYY-MM-DD or null")
        return None


def normal_set(values, path, validation):
    if values is None:
        return set()
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        validation.append(f"{path} must be a list of strings")
        return set()
    return {x.strip().casefold() for x in values}


def add_check(state, message, reasons, unknown):
    if state is False:
        reasons.append(message)
    elif state is None:
        unknown.append(message)


def classify(candidate, customer, requirements, validation):
    name = candidate.get("name")
    label = name if isinstance(name, str) and name.strip() else "unnamed candidate"
    reasons, unknown = [], []

    desired_type = requirements.get("desired_product_type")
    product_type = candidate.get("product_type")
    if desired_type is not None:
        if not isinstance(desired_type, str):
            validation.append("requirements.desired_product_type must be a string or null")
        elif product_type is None:
            unknown.append("product type is not documented")
        elif not isinstance(product_type, str):
            validation.append(f"candidate {label}: product_type must be a string or null")
        elif product_type.casefold() != desired_type.casefold():
            reasons.append(f"product type is {product_type}, not {desired_type}")

    score = decimal_or_none(customer.get("credit_score"), "customer.credit_score", validation)
    minimum_score = decimal_or_none(candidate.get("minimum_credit_score"),
                                    f"candidate {label}: minimum_credit_score", validation)
    no_score_requirement = candidate.get("minimum_credit_score_means_no_requirement", False)
    if not isinstance(no_score_requirement, bool):
        validation.append(f"candidate {label}: minimum_credit_score_means_no_requirement must be boolean")
        no_score_requirement = False
    if minimum_score is None:
        unknown.append("minimum credit-score requirement is not documented")
    elif minimum_score == 0 and no_score_requirement:
        pass
    elif score is None:
        unknown.append("customer credit score was not supplied")
    elif score < minimum_score:
        reasons.append(f"credit score is below the documented minimum of {minimum_score}")

    memberships = normal_set(customer.get("memberships", []), "customer.memberships", validation)
    required = candidate.get("required_memberships", [])
    required_set = normal_set(required, f"candidate {label}: required_memberships", validation)
    missing_memberships = sorted(required_set - memberships)
    if missing_memberships:
        reasons.append("missing required membership(s): " + ", ".join(missing_memberships))

    fee_max = decimal_or_none(requirements.get("foreign_transaction_fee_max_pct"),
                              "requirements.foreign_transaction_fee_max_pct", validation)
    if fee_max is not None:
        fee = decimal_or_none(candidate.get("foreign_transaction_fee_percent"),
                              f"candidate {label}: foreign_transaction_fee_percent", validation)
        if fee is None:
            unknown.append("foreign transaction fee is not documented")
        elif fee > fee_max:
            reasons.append(f"foreign transaction fee {fee}% exceeds {fee_max}%")

    payment_max = decimal_or_none(requirements.get("minimum_payment_max_pct"),
                                  "requirements.minimum_payment_max_pct", validation)
    if payment_max is not None:
        payment = decimal_or_none(candidate.get("minimum_payment_percent"),
                                  f"candidate {label}: minimum_payment_percent", validation)
        basis = candidate.get("minimum_payment_basis")
        accepted_bases = requirements.get("accepted_min_payment_bases", ["statement_balance"])
        if not isinstance(accepted_bases, list) or not all(isinstance(x, str) for x in accepted_bases):
            validation.append("requirements.accepted_min_payment_bases must be a list of strings")
            accepted_bases = []
        accepted_bases = {x.casefold() for x in accepted_bases}
        if payment is None:
            unknown.append("minimum-payment percentage is not documented")
        elif payment > payment_max:
            reasons.append(f"minimum payment {payment}% exceeds {payment_max}%")
        if basis is None or basis == "unknown":
            unknown.append("minimum-payment balance basis is not documented")
        elif not isinstance(basis, str):
            validation.append(f"candidate {label}: minimum_payment_basis must be a string or null")
        elif basis.casefold() not in accepted_bases:
            reasons.append(f"minimum-payment basis {basis} is not accepted")

    if requirements.get("require_virtual_card_management") is True:
        virtual = candidate.get("virtual_card_management")
        if virtual is True:
            pass
        elif virtual is False:
            reasons.append("virtual card management is not available")
        else:
            unknown.append("virtual card-management availability is not documented")

    as_of = parse_date(requirements.get("as_of"), "requirements.as_of", validation)
    start = parse_date(candidate.get("available_from"), f"candidate {label}: available_from", validation)
    end = parse_date(candidate.get("available_through"), f"candidate {label}: available_through", validation)
    if start is not None or end is not None:
        if as_of is None:
            unknown.append("date is needed to assess the offer window")
        elif start is not None and as_of < start:
            reasons.append("offer is not yet active on the supplied date")
        elif end is not None and as_of > end:
            reasons.append("offer expired before the supplied date")

    checks = candidate.get("eligibility_checks", {})
    if not isinstance(checks, dict):
        validation.append(f"candidate {label}: eligibility_checks must be an object")
    else:
        for condition, value in checks.items():
            if value is False:
                reasons.append(f"documented eligibility condition not met: {condition}")
            elif value is None or value == "unknown":
                unknown.append(f"documented eligibility condition is unconfirmed: {condition}")
            elif value is not True:
                validation.append(f"candidate {label}: eligibility_checks[{condition!r}] must be true, false, or 'unknown'")

    result = {"name": label, "source_ids": candidate.get("source_ids", []), "reasons": reasons, "unknown": unknown}
    if reasons:
        return "disqualified", result
    if unknown:
        return "uncertain", result
    return "qualified", result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "error", "error": f"invalid JSON: {exc.msg}"}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"status": "error", "error": "top-level JSON must be an object"}))
        return

    customer = payload.get("customer", {})
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    validation = []
    if not isinstance(customer, dict): validation.append("customer must be an object"); customer = {}
    if not isinstance(requirements, dict): validation.append("requirements must be an object"); requirements = {}
    if not isinstance(candidates, list): validation.append("candidates must be a list"); candidates = []

    output = {"status": "ok", "qualified": [], "disqualified": [], "uncertain": [], "validation": validation}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            validation.append(f"candidates[{index}] must be an object")
            continue
        bucket, result = classify(candidate, customer, requirements, validation)
        output[bucket].append(result)
    print(json.dumps(output, default=str, sort_keys=True))


if __name__ == "__main__":
    main()
