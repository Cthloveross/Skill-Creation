#!/usr/bin/env python3
"""Rank caller-supplied, extracted credit-card terms without retrieving data."""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def failure(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "recommendations": [], "excluded": [], "errors": errors}


def decimal_value(value: Any, field: str, errors: list[str], required: bool = False) -> Decimal | None:
    if value is None:
        if required:
            errors.append(f"{field} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{field} must be finite and nonnegative")
        return None
    return number


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return failure(["input must be an object"])
    preferences = data.get("preferences")
    offers = data.get("offers")
    if not isinstance(preferences, dict) or not isinstance(offers, list) or not offers:
        return failure(["preferences must be an object and offers must be a nonempty array"])

    errors: list[str] = []
    personal_only = preferences.get("personal_only", True)
    simple_flat = preferences.get("simple_flat_rate", False)
    maximum_fee = decimal_value(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    customer_score = decimal_value(preferences.get("credit_score"), "preferences.credit_score", errors)
    confirmed = preferences.get("confirmed_requirements", {})
    if not isinstance(personal_only, bool) or not isinstance(simple_flat, bool):
        errors.append("personal_only and simple_flat_rate must be boolean")
    if not isinstance(confirmed, dict) or any(not isinstance(k, str) or not isinstance(v, bool) for k, v in confirmed.items()):
        errors.append("confirmed_requirements must map strings to booleans")
        confirmed = {}
    if errors:
        return failure(errors)

    recommendations: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            errors.append(f"offers[{index}] must be an object")
            continue
        name = offer.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"offers[{index}].name must be a nonempty string")
            continue
        name = name.strip()
        personal = offer.get("personal", True)
        flat = offer.get("flat_all_purchases", False)
        invitation_only = offer.get("invitation_only", False)
        requirements = offer.get("requirements", [])
        if any(not isinstance(v, bool) for v in (personal, flat, invitation_only)):
            errors.append(f"{name} has invalid boolean flags")
            continue
        if not isinstance(requirements, list) or any(not isinstance(v, str) or not v.strip() for v in requirements):
            errors.append(f"{name}.requirements must be an array of nonempty strings")
            continue
        rate = decimal_value(offer.get("cash_back_rate_percent"), f"{name}.cash_back_rate_percent", errors, True)
        fee = decimal_value(offer.get("annual_fee"), f"{name}.annual_fee", errors, True)
        minimum_score = decimal_value(offer.get("min_credit_score"), f"{name}.min_credit_score", errors)
        if rate is None or fee is None:
            continue

        reasons: list[str] = []
        unresolved: list[str] = []
        if personal_only and not personal:
            reasons.append("not a personal card")
        if simple_flat and not flat:
            reasons.append("not flat all-purchases rewards")
        if maximum_fee is not None and fee > maximum_fee:
            reasons.append("annual fee exceeds customer limit")
        if invitation_only:
            reasons.append("invitation-only")
        for requirement in requirements:
            state = confirmed.get(requirement)
            if state is False:
                reasons.append(f"known unmet requirement: {requirement}")
            elif state is not True:
                unresolved.append(requirement)
        if minimum_score is not None:
            if customer_score is None:
                unresolved.append(f"minimum credit score {minimum_score}")
            elif customer_score < minimum_score:
                reasons.append("credit score below documented minimum")
        if reasons:
            excluded.append({"name": name, "reasons": reasons})
        else:
            recommendations.append({
                "name": name,
                "cash_back_rate_percent": float(rate),
                "annual_fee": float(fee),
                "unresolved_conditions": sorted(set(unresolved)),
                "_rate": rate,
            })

    if errors:
        return failure(errors)
    recommendations.sort(key=lambda item: (-item["_rate"], item["annual_fee"], item["name"].casefold()))
    for item in recommendations:
        del item["_rate"]
    return {
        "ok": True,
        "recommendations": recommendations,
        "excluded": excluded,
        "errors": [],
        "interpretation": "Disclose unresolved conditions and do not infer approval.",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(failure([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
