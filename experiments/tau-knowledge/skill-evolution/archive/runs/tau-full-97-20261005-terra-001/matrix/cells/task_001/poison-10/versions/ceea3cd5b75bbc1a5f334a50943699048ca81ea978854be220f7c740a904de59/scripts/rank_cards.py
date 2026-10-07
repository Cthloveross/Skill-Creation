#!/usr/bin/env python3
"""Rank current-task cash-back-card terms supplied as JSON on stdin."""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def result_error(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "recommendations": [], "excluded": [], "errors": errors}


def number(value: Any, label: str, errors: list[str], nullable: bool = True) -> Decimal | None:
    if value is None:
        if not nullable:
            errors.append(f"{label} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be a number")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a number")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(f"{label} must be a finite number at least 0")
        return None
    return parsed


def money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return result_error(["input must be a JSON object"])
    preferences = payload.get("preferences")
    offers = payload.get("offers")
    if not isinstance(preferences, dict) or not isinstance(offers, list) or not offers:
        errors = []
        if not isinstance(preferences, dict):
            errors.append("preferences must be an object")
        if not isinstance(offers, list) or not offers:
            errors.append("offers must be a nonempty array")
        return result_error(errors)

    errors: list[str] = []
    personal_only = preferences.get("personal_only", True)
    flat_preference = preferences.get("simple_flat_rate", False)
    if not isinstance(personal_only, bool):
        errors.append("preferences.personal_only must be boolean")
    if not isinstance(flat_preference, bool):
        errors.append("preferences.simple_flat_rate must be boolean")
    maximum_fee = number(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    monthly_spend = number(preferences.get("monthly_eligible_spend"), "preferences.monthly_eligible_spend", errors)
    customer_score = number(preferences.get("credit_score"), "preferences.credit_score", errors)
    confirmed = preferences.get("confirmed_requirements", {})
    if not isinstance(confirmed, dict) or any(
        not isinstance(key, str) or not key or not isinstance(value, bool)
        for key, value in confirmed.items()
    ):
        errors.append("preferences.confirmed_requirements must map nonempty strings to booleans")
        confirmed = {}
    if errors:
        return result_error(errors)

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
        flat_rate = offer.get("flat_rate", False)
        invitation_only = offer.get("invitation_only", False)
        requires = offer.get("requires", {})
        if not all(isinstance(value, bool) for value in (personal, flat_rate, invitation_only)):
            errors.append(f"{name}: personal, flat_rate, and invitation_only must be boolean")
            continue
        if not isinstance(requires, dict) or any(
            not isinstance(key, str) or not key or not isinstance(value, bool)
            for key, value in requires.items()
        ):
            errors.append(f"{name}.requires must map nonempty strings to booleans")
            continue
        item_errors: list[str] = []
        rate = number(offer.get("cash_back_rate_percent"), f"{name}.cash_back_rate_percent", item_errors, False)
        fee = number(offer.get("annual_fee"), f"{name}.annual_fee", item_errors, False)
        minimum_score = number(offer.get("min_credit_score"), f"{name}.min_credit_score", item_errors)
        if item_errors:
            errors.extend(item_errors)
            continue

        reasons: list[str] = []
        unresolved: list[str] = []
        if personal_only and not personal:
            reasons.append("not a personal card")
        if flat_preference and not flat_rate:
            reasons.append("not a flat-rate card")
        if maximum_fee is not None and fee is not None and fee > maximum_fee:
            reasons.append("annual fee exceeds customer limit")
        if invitation_only:
            reasons.append("invitation-only status is a known restriction")
        for requirement, required in requires.items():
            if required:
                if confirmed.get(requirement) is False:
                    reasons.append(f"required condition not met: {requirement}")
                elif confirmed.get(requirement) is not True:
                    unresolved.append(requirement)
        if minimum_score is not None:
            if customer_score is None:
                unresolved.append("minimum credit score")
            elif customer_score < minimum_score:
                reasons.append("credit score is below stated minimum")
        if reasons:
            excluded.append({"name": name, "reasons": reasons})
            continue

        annual_net = None
        if monthly_spend is not None and rate is not None and fee is not None:
            annual_net = monthly_spend * Decimal("12") * rate / Decimal("100") - fee
        recommendations.append({
            "name": name,
            "cash_back_rate_percent": float(rate),
            "annual_fee": money(fee),
            "flat_rate": flat_rate,
            "unresolved_conditions": sorted(set(unresolved)),
            "estimated_annual_net_rewards": money(annual_net) if annual_net is not None else None,
            "_sort_value": annual_net if annual_net is not None else rate,
        })

    if errors:
        return result_error(errors)
    recommendations.sort(key=lambda card: (
        -card["_sort_value"], card["annual_fee"], len(card["unresolved_conditions"]), card["name"].casefold()
    ))
    for card in recommendations:
        del card["_sort_value"]
    return {
        "ok": True,
        "recommendations": recommendations,
        "excluded": excluded,
        "errors": [],
        "interpretation": "Disclose unresolved eligibility and approval conditions in the final response.",
    }


def run() -> None:
    try:
        payload = json.load(sys.stdin)
        output = main(payload)
    except json.JSONDecodeError as exc:
        output = result_error([f"invalid JSON input: {exc.msg}"])
    except Exception as exc:
        output = result_error([f"unable to process input: {exc}"])
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    run()
