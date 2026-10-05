#!/usr/bin/env python3
"""Rank documented card offers supplied as a JSON object on stdin."""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def error(messages: list[str]) -> dict[str, Any]:
    return {"ok": False, "recommendations": [], "excluded": [], "errors": messages}


def numeric(value: Any, label: str, errors: list[str], required: bool = False) -> Decimal | None:
    if value is None:
        if required:
            errors.append(f"{label} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a finite number at least zero")
        return None
    return result


def main(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return error(["input must be a JSON object"])
    preferences, offers = data.get("preferences"), data.get("offers")
    if not isinstance(preferences, dict) or not isinstance(offers, list) or not offers:
        return error(["preferences must be an object", "offers must be a nonempty array"])

    errors: list[str] = []
    personal_only = preferences.get("personal_only", True)
    simple_flat_rate = preferences.get("simple_flat_rate", False)
    if not isinstance(personal_only, bool) or not isinstance(simple_flat_rate, bool):
        errors.append("personal_only and simple_flat_rate must be boolean")
    maximum_fee = numeric(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    monthly_spend = numeric(preferences.get("monthly_eligible_spend"), "preferences.monthly_eligible_spend", errors)
    customer_score = numeric(preferences.get("credit_score"), "preferences.credit_score", errors)
    confirmed = preferences.get("confirmed_requirements", {})
    if not isinstance(confirmed, dict) or any(not isinstance(k, str) or not k or not isinstance(v, bool) for k, v in confirmed.items()):
        errors.append("confirmed_requirements must map nonempty strings to booleans")
        confirmed = {}
    if errors:
        return error(errors)

    recommended, excluded = [], []
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
        flat = offer.get("flat_rate", False)
        invitation = offer.get("invitation_only", False)
        requires = offer.get("requires", {})
        if not all(isinstance(x, bool) for x in (personal, flat, invitation)) or not isinstance(requires, dict):
            errors.append(f"{name} has invalid boolean flags or requirements")
            continue
        rate = numeric(offer.get("cash_back_rate_percent"), f"{name}.cash_back_rate_percent", errors, True)
        fee = numeric(offer.get("annual_fee"), f"{name}.annual_fee", errors, True)
        min_score = numeric(offer.get("min_credit_score"), f"{name}.min_credit_score", errors)
        if rate is None or fee is None:
            continue
        reasons, unresolved = [], []
        if personal_only and not personal:
            reasons.append("not a personal card")
        if simple_flat_rate and not flat:
            reasons.append("not a flat-rate card")
        if maximum_fee is not None and fee > maximum_fee:
            reasons.append("annual fee exceeds customer limit")
        if invitation:
            reasons.append("invitation-only restriction")
        for requirement, required in requires.items():
            if not isinstance(requirement, str) or not requirement or not isinstance(required, bool):
                errors.append(f"{name}.requires must map nonempty strings to booleans")
                continue
            if required and confirmed.get(requirement) is False:
                reasons.append(f"required condition not met: {requirement}")
            elif required and confirmed.get(requirement) is not True:
                unresolved.append(requirement)
        if min_score is not None:
            if customer_score is None:
                unresolved.append("minimum credit score")
            elif customer_score < min_score:
                reasons.append("credit score is below stated minimum")
        if reasons:
            excluded.append({"name": name, "reasons": reasons})
            continue
        annual_estimate = None if monthly_spend is None else monthly_spend * Decimal(12) * rate / Decimal(100) - fee
        recommended.append({
            "name": name, "cash_back_rate_percent": float(rate), "annual_fee": float(fee),
            "unresolved_conditions": sorted(set(unresolved)),
            "estimated_annual_net_rewards": None if annual_estimate is None else float(annual_estimate.quantize(Decimal("0.01"))),
            "_sort": annual_estimate if annual_estimate is not None else rate,
        })
    if errors:
        return error(errors)
    recommended.sort(key=lambda item: (-item["_sort"], item["annual_fee"], item["name"].casefold()))
    for item in recommended:
        del item["_sort"]
    return {"ok": True, "recommendations": recommended, "excluded": excluded, "errors": [], "interpretation": "Disclose all unresolved conditions and do not infer approval."}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(error([f"invalid JSON input: {exc.msg}"],), sort_keys=True))
