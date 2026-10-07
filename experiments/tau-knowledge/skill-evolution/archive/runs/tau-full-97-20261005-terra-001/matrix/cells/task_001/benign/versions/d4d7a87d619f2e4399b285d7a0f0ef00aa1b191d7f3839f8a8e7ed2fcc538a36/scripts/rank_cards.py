#!/usr/bin/env python3
"""Rank normalized cash-back card candidates.

Reads the JSON schema documented in SKILL.md from stdin and writes a JSON object
with ranked viable candidates, excluded candidates, and validation errors.
"""

import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple


def number(value: Any) -> Optional[float]:
    """Return a finite numeric value, excluding booleans and non-numeric input."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    return None


def text(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def evaluate_requirement(requirement: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[str, str]:
    """Return eligibility state (eligible/conditional/ineligible) and reason."""
    req_type = text(requirement.get("type"))
    key = str(requirement.get("key", "requirement"))
    profile_key = str(requirement.get("profile_key") or key)
    label = str(requirement.get("label") or key.replace("_", " "))
    target = requirement.get("value")

    if req_type == "minimum_number":
        # ``profile_key`` permits a term name such as minimum_credit_score to map
        # to the customer field credit_score. The fallback maintains compatibility
        # with records where the two names are identical.
        actual = number(profile.get(profile_key))
        minimum = number(target)
        if minimum is None:
            return "conditional", f"The documented {label} is not numerically usable."
        if actual is None:
            return "conditional", f"Confirm {label} of at least {minimum:g}."
        if actual < minimum:
            return "ineligible", f"Requires {label} of at least {minimum:g}; supplied value is {actual:g}."
        return "eligible", ""

    if req_type == "required_boolean":
        requirements = profile.get("requirements")
        actual = requirements.get(key) if isinstance(requirements, dict) else None
        if actual is None:
            return "conditional", f"Confirm required {label}."
        if actual != target:
            return "ineligible", f"Does not meet required {label}."
        return "eligible", ""

    return "conditional", f"Confirm unsupported requirement type for {label}."


def applicable_rate(card: Dict[str, Any], categories: List[str], weights: Dict[str, Any]) -> Tuple[Optional[float], List[str]]:
    """Calculate weighted applicable rate using supported category rates or default."""
    default = number(card.get("default_cash_back_percent"))
    category_rates = card.get("category_cash_back_percent")
    category_rates = category_rates if isinstance(category_rates, dict) else {}
    if not categories:
        return default, [] if default is not None else ["No documented default cash-back rate."]

    weighted_total = 0.0
    weight_total = 0.0
    caveats: List[str] = []
    for category in categories:
        normalized = text(category)
        if not normalized:
            continue
        rate = number(category_rates.get(normalized))
        if rate is None:
            rate = default
        if rate is None:
            caveats.append(f"No documented applicable rate for {normalized}.")
            continue
        weight = number(weights.get(normalized)) if isinstance(weights, dict) else None
        weight = weight if weight is not None and weight > 0 else 1.0
        weighted_total += rate * weight
        weight_total += weight

    if weight_total == 0:
        return None, caveats or ["No usable spending categories or rates."]
    return weighted_total / weight_total, caveats


def evaluate_card(card: Dict[str, Any], preferences: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate constraints, unresolved requirements, and applicable earn rate."""
    name = str(card.get("name") or "Unnamed card")
    excluded_reasons: List[str] = []
    conditional_reasons: List[str] = []
    annual_fee = number(card.get("annual_fee"))
    max_fee = number(preferences.get("max_annual_fee"))

    if max_fee is not None:
        if annual_fee is None:
            conditional_reasons.append("Confirm the annual fee; supplied documents did not establish it.")
        elif annual_fee > max_fee:
            excluded_reasons.append(f"Annual fee {annual_fee:g} exceeds the maximum {max_fee:g}.")

    if card.get("invitation_only") is True:
        profile_requirements = profile.get("requirements")
        invited = profile_requirements.get("invitation_only") if isinstance(profile_requirements, dict) else None
        if invited is not True:
            if invited is False:
                excluded_reasons.append("Card is invitation-only and the profile says no invitation is held.")
            else:
                excluded_reasons.append("Card is invitation-only; invitation status is not established.")

    requirements = card.get("requirements")
    if isinstance(requirements, list):
        for requirement in requirements:
            if not isinstance(requirement, dict):
                conditional_reasons.append("A documented requirement could not be interpreted.")
                continue
            state, reason = evaluate_requirement(requirement, profile)
            if state == "ineligible":
                excluded_reasons.append(reason)
            elif state == "conditional":
                conditional_reasons.append(reason)

    categories = preferences.get("categories")
    categories = categories if isinstance(categories, list) else []
    weights = preferences.get("category_weights")
    weights = weights if isinstance(weights, dict) else {}
    rate, rate_caveats = applicable_rate(card, categories, weights)
    if rate is None:
        excluded_reasons.extend(rate_caveats)
    else:
        conditional_reasons.extend(rate_caveats)

    if excluded_reasons:
        status = "ineligible"
    elif conditional_reasons:
        status = "conditional"
    else:
        status = "eligible"

    return {
        "name": name,
        "annual_fee": annual_fee,
        "applicable_cash_back_percent": rate,
        "eligibility_status": status,
        "conditional_reasons": conditional_reasons,
        "exclusion_reasons": excluded_reasons,
        "source_titles": card.get("source_titles") if isinstance(card.get("source_titles"), list) else [],
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a ranking request and return deterministic candidate ordering."""
    errors: List[str] = []
    preferences = payload.get("preferences")
    profile = payload.get("profile")
    cards = payload.get("cards")
    if not isinstance(preferences, dict):
        errors.append("preferences must be an object.")
        preferences = {}
    if not isinstance(profile, dict):
        errors.append("profile must be an object.")
        profile = {}
    if not isinstance(cards, list):
        errors.append("cards must be an array.")
        cards = []

    evaluated: List[Dict[str, Any]] = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append(f"cards[{index}] must be an object.")
            continue
        if not str(card.get("name") or "").strip():
            errors.append(f"cards[{index}] is missing a name.")
            continue
        evaluated.append(evaluate_card(card, preferences, profile))

    viable = [candidate for candidate in evaluated if candidate["eligibility_status"] != "ineligible"]
    excluded = [candidate for candidate in evaluated if candidate["eligibility_status"] == "ineligible"]
    status_rank = {"eligible": 0, "conditional": 1}
    viable.sort(key=lambda candidate: (
        -(candidate["applicable_cash_back_percent"] if candidate["applicable_cash_back_percent"] is not None else -1),
        status_rank.get(candidate["eligibility_status"], 2),
        candidate["annual_fee"] if candidate["annual_fee"] is not None else float("inf"),
        candidate["name"].lower(),
    ))

    recommendation = viable[0] if viable else None
    return {
        "errors": errors,
        "ranked_candidates": viable,
        "excluded": excluded,
        "recommendation": recommendation,
        "interpretation": (
            "A conditional recommendation requires confirmation of every listed condition; it is not an approval decision."
            if recommendation and recommendation["eligibility_status"] == "conditional"
            else "Ranking uses documented applicable cash-back rates and known hard constraints."
        ),
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(raw), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"errors": [str(exc)], "ranked_candidates": [], "excluded": [], "recommendation": None}))
        sys.exit(1)
