#!/usr/bin/env python3
"""Rank structured, current-task cash-back-card offers.

Read one JSON object from stdin and emit one JSON object on stdout. The helper
is catalog-free: callers provide terms extracted from current source material.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Optional


def failure(errors: list[str]) -> dict[str, Any]:
    return {"ok": False, "recommendations": [], "excluded": [], "errors": errors}


def decimal_value(value: Any, label: str, errors: list[str], minimum: Decimal = Decimal("0")) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be a number or null, not a boolean")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a number or null")
        return None
    if not number.is_finite() or number < minimum:
        errors.append(f"{label} must be a finite number at least {minimum}")
        return None
    return number


def rounded_money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return failure(["input must be a JSON object"])

    preferences = payload.get("preferences")
    offers = payload.get("offers")
    errors: list[str] = []
    if not isinstance(preferences, dict):
        errors.append("preferences must be an object")
    if not isinstance(offers, list) or not offers:
        errors.append("offers must be a nonempty array")
    if errors:
        return failure(errors)

    personal_only = preferences.get("personal_only", True)
    simple_flat_rate = preferences.get("simple_flat_rate", False)
    if not isinstance(personal_only, bool):
        errors.append("preferences.personal_only must be boolean")
    if not isinstance(simple_flat_rate, bool):
        errors.append("preferences.simple_flat_rate must be boolean")

    max_fee = decimal_value(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    monthly_spend = decimal_value(preferences.get("monthly_eligible_spend"), "preferences.monthly_eligible_spend", errors)
    credit_score = decimal_value(preferences.get("credit_score"), "preferences.credit_score", errors)
    confirmed = preferences.get("confirmed_requirements", {})
    if not isinstance(confirmed, dict) or any(not isinstance(k, str) or not k or not isinstance(v, bool) for k, v in confirmed.items()):
        errors.append("preferences.confirmed_requirements must map nonempty strings to booleans")
        confirmed = {}
    if errors:
        return failure(errors)

    candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for index, offer in enumerate(offers):
        label = f"offers[{index}]"
        if not isinstance(offer, dict):
            errors.append(f"{label} must be an object")
            continue
        name = offer.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name must be a nonempty string")
            continue
        name = name.strip()
        personal = offer.get("personal", True)
        flat_rate = offer.get("flat_rate", False)
        requires = offer.get("requires", {})
        item_errors: list[str] = []
        if not isinstance(personal, bool):
            item_errors.append(f"{name}.personal must be boolean")
        if not isinstance(flat_rate, bool):
            item_errors.append(f"{name}.flat_rate must be boolean")
        if not isinstance(requires, dict):
            item_errors.append(f"{name}.requires must be an object")
            requires = {}
        rate = decimal_value(offer.get("cash_back_rate_percent"), f"{name}.cash_back_rate_percent", item_errors)
        fee = decimal_value(offer.get("annual_fee"), f"{name}.annual_fee", item_errors)
        minimum_score = decimal_value(offer.get("min_credit_score"), f"{name}.min_credit_score", item_errors)
        if item_errors:
            errors.extend(item_errors)
            continue

        reasons: list[str] = []
        unresolved: list[str] = []
        if personal_only and not personal:
            reasons.append("not a personal card")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual fee exceeds the customer limit")

        for key, required in requires.items():
            if not isinstance(key, str) or not key:
                errors.append(f"{name}.requires keys must be nonempty strings")
                continue
            if not isinstance(required, bool):
                errors.append(f"{name}.requires.{key} must be boolean")
                continue
            if required:
                status = confirmed.get(key)
                if status is False:
                    reasons.append(f"required condition not met: {key}")
                elif status is not True:
                    unresolved.append(key)

        if minimum_score is not None:
            if credit_score is None:
                unresolved.append("minimum credit score")
            elif credit_score < minimum_score:
                reasons.append("credit score is below the stated minimum")

        if reasons:
            excluded.append({"name": name, "reasons": reasons})
            continue

        annual_net = None
        if monthly_spend is not None and rate is not None and fee is not None:
            annual_net = monthly_spend * Decimal("12") * rate / Decimal("100") - fee
        candidates.append({
            "name": name,
            "cash_back_rate_percent": float(rate),
            "annual_fee": rounded_money(fee),
            "flat_rate": flat_rate,
            "unresolved_conditions": sorted(set(unresolved)),
            "estimated_annual_net_rewards": rounded_money(annual_net) if annual_net is not None else None,
            "_value": annual_net if annual_net is not None else rate,
        })

    if errors:
        return failure(errors)

    # Explicit conflicts are already excluded. For remaining offers, prioritize
    # the customer's reward style and documented value. Unresolved conditions
    # remain visible to the caller rather than silently converting to approval.
    candidates.sort(key=lambda card: (
        0 if (not simple_flat_rate or card["flat_rate"]) else 1,
        -card["_value"],
        card["annual_fee"],
        len(card["unresolved_conditions"]),
        card["name"].casefold(),
    ))
    for card in candidates:
        del card["_value"]

    return {
        "ok": True,
        "recommendations": candidates,
        "excluded": excluded,
        "errors": [],
        "interpretation": "Rank order is decision support only; disclose unresolved eligibility and underwriting conditions.",
    }


def run() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(failure([f"invalid JSON input: {exc.msg}"]), sort_keys=True))
        return
    except Exception as exc:
        print(json.dumps(failure([f"unable to read input: {exc}"]), sort_keys=True))
        return
    print(json.dumps(main(payload), sort_keys=True))


if __name__ == "__main__":
    run()
