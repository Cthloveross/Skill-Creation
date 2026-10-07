#!/usr/bin/env python3
"""Rank supplied cash-back card records under documented customer constraints.

Input and output are JSON objects as described in SKILL.md. This script evaluates
only the terms passed to it. It neither accesses customer accounts nor makes an
application, eligibility, or underwriting decision.
"""

import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple


def clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def numeric(value: Any) -> Optional[float]:
    """Return a finite numeric value; booleans and numeric strings are rejected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def format_number(value: Optional[float]) -> str:
    return "unknown" if value is None else f"{value:g}"


def profile_boolean(profile: Dict[str, Any], key: str) -> Optional[bool]:
    """Return only explicit boolean customer evidence; all other values are unknown."""
    requirements = profile.get("requirements")
    if not isinstance(requirements, dict):
        return None
    value = requirements.get(key)
    return value if isinstance(value, bool) else None


def requirement_state(requirement: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (eligible|conditional|ineligible, explanation, confirmed label)."""
    kind = clean(requirement.get("type")).lower()
    key = clean(requirement.get("key"))
    profile_key = clean(requirement.get("profile_key")) or key
    label = clean(requirement.get("label")) or key.replace("_", " ") or "requirement"

    if kind == "minimum_number":
        threshold = numeric(requirement.get("value"))
        actual = numeric(profile.get(profile_key))
        if threshold is None:
            return "conditional", f"Confirm the documented {label}.", ""
        if actual is None:
            return "conditional", f"Confirm that you meet the {label} of at least {format_number(threshold)}.", ""
        if actual < threshold:
            return (
                "ineligible",
                f"Requires a {label} of at least {format_number(threshold)}; the supplied value is {format_number(actual)}.",
                "",
            )
        return "eligible", "", label

    if kind == "required_boolean":
        target = requirement.get("value")
        if not isinstance(target, bool):
            return "conditional", f"Confirm the documented {label}.", ""
        actual = profile_boolean(profile, key)
        if actual is None:
            return "conditional", f"Confirm the required {label} is active and qualifies.", ""
        if actual != target:
            return "ineligible", f"Does not currently meet the required {label}.", ""
        return "eligible", "", label

    return "conditional", f"Confirm the documented requirement: {label}.", ""


def applicable_rate(card: Dict[str, Any], categories: List[Any], weights: Dict[str, Any]) -> Tuple[Optional[float], List[str]]:
    """Calculate a weighted rate, using the default outside documented bonuses."""
    default = numeric(card.get("default_cash_back_percent"))
    category_rates = card.get("category_cash_back_percent")
    category_rates = category_rates if isinstance(category_rates, dict) else {}

    if not categories:
        return default, [] if default is not None else ["No documented applicable cash-back rate."]

    weighted_total = 0.0
    total_weight = 0.0
    errors: List[str] = []
    for raw_category in categories:
        category = clean(raw_category).lower()
        if not category:
            continue
        rate = numeric(category_rates.get(category))
        if rate is None:
            rate = default
        if rate is None:
            errors.append(f"No documented applicable cash-back rate for {category}.")
            continue
        weight = numeric(weights.get(category))
        weight = weight if weight is not None and weight > 0 else 1.0
        weighted_total += rate * weight
        total_weight += weight

    if total_weight == 0:
        return None, errors or ["No usable spending category and rate were supplied."]
    return weighted_total / total_weight, errors


def evaluate_card(card: Dict[str, Any], preferences: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Apply known hard constraints and preserve unknown requirements as conditions."""
    name = clean(card.get("name")) or "Unnamed card"
    exclusions: List[str] = []
    conditions: List[str] = []
    confirmed: List[str] = []

    fee = numeric(card.get("annual_fee"))
    ceiling = numeric(preferences.get("max_annual_fee"))
    if ceiling is not None:
        if fee is None:
            exclusions.append("Annual fee is not documented, so compatibility with the fee limit cannot be established.")
        elif fee > ceiling:
            exclusions.append(f"Annual fee ${format_number(fee)} exceeds the maximum ${format_number(ceiling)}.")

    if card.get("invitation_only") is True and profile_boolean(profile, "invitation_only") is not True:
        exclusions.append("Card is invitation-only and an invitation is not confirmed.")

    raw_requirements = card.get("requirements")
    if isinstance(raw_requirements, list):
        for requirement in raw_requirements:
            if not isinstance(requirement, dict):
                conditions.append("Confirm an unreadable documented requirement.")
                continue
            state, reason, label = requirement_state(requirement, profile)
            if state == "ineligible":
                exclusions.append(reason)
            elif state == "conditional":
                conditions.append(reason)
            elif label:
                confirmed.append(label)

    raw_categories = preferences.get("categories")
    categories = raw_categories if isinstance(raw_categories, list) else []
    raw_weights = preferences.get("category_weights")
    weights = raw_weights if isinstance(raw_weights, dict) else {}
    rate, rate_errors = applicable_rate(card, categories, weights)
    exclusions.extend(rate_errors)

    status = "ineligible" if exclusions else ("conditional" if conditions else "eligible")
    source_titles = card.get("source_titles")
    return {
        "name": name,
        "annual_fee": fee,
        "applicable_cash_back_percent": rate,
        "rate_scope": clean(card.get("rate_scope")) or "at the documented applicable rate",
        "eligibility_status": status,
        "conditional_reasons": conditions,
        "confirmed_requirements": confirmed,
        "exclusion_reasons": exclusions,
        "source_titles": source_titles if isinstance(source_titles, list) else [],
    }


def draft_message(candidate: Optional[Dict[str, Any]], preferences: Dict[str, Any]) -> str:
    """Create factual customer-facing wording without representing an approval."""
    if candidate is None:
        return "No supported recommendation is available from the supplied comparable terms."

    name = candidate["name"]
    rate = format_number(candidate["applicable_cash_back_percent"])
    fee = format_number(candidate["annual_fee"])
    conditional = candidate["eligibility_status"] == "conditional"
    message = f"Recommendation: {name}" + (", conditionally." if conditional else ".")
    message += f" It earns {rate}% cash back {candidate['rate_scope']} and has a ${fee} annual fee."

    ceiling = numeric(preferences.get("max_annual_fee"))
    card_fee = candidate["annual_fee"]
    if ceiling is not None and card_fee is not None and card_fee <= ceiling:
        message += " That meets your stated annual-fee limit."
    if candidate["confirmed_requirements"]:
        message += " Your confirmed " + ", ".join(candidate["confirmed_requirements"]) + " satisfies that documented requirement."
    if candidate["conditional_reasons"]:
        message += " " + " ".join(candidate["conditional_reasons"])
    message += " This comparison is not an approval; final eligibility and approval are subject to underwriting."
    return message


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
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
        if not clean(card.get("name")):
            errors.append(f"cards[{index}] is missing a name.")
            continue
        evaluated.append(evaluate_card(card, preferences, profile))

    viable = [item for item in evaluated if item["eligibility_status"] != "ineligible"]
    excluded = [item for item in evaluated if item["eligibility_status"] == "ineligible"]
    status_order = {"eligible": 0, "conditional": 1}
    viable.sort(key=lambda item: (
        -(item["applicable_cash_back_percent"] if item["applicable_cash_back_percent"] is not None else -1),
        status_order.get(item["eligibility_status"], 2),
        item["annual_fee"] if item["annual_fee"] is not None else float("inf"),
        item["name"].lower(),
    ))
    recommendation = viable[0] if viable else None
    return {
        "errors": errors,
        "ranked_candidates": viable,
        "excluded": excluded,
        "recommendation": recommendation,
        "customer_message": draft_message(recommendation, preferences),
        "interpretation": "A conditional result requires confirmation of every listed condition and is not an approval decision.",
    }


if __name__ == "__main__":
    try:
        raw_payload = json.load(sys.stdin)
        if not isinstance(raw_payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(raw_payload), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({
            "errors": [str(error)],
            "ranked_candidates": [],
            "excluded": [],
            "recommendation": None,
            "customer_message": "Unable to compare the supplied terms.",
        }, ensure_ascii=False, sort_keys=True))
        sys.exit(1)
