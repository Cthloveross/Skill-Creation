#!/usr/bin/env python3
"""Deterministically rank supplied cash-back card records.

Read one JSON object from stdin using the schema in SKILL.md and write one JSON
object to stdout. This helper only evaluates supplied terms; it makes no account
changes and does not make an underwriting or approval decision.
"""

import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple


def numeric(value: Any) -> Optional[float]:
    """Return a finite number, excluding booleans and strings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def format_number(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{value:g}"


def requirement_state(requirement: Dict[str, Any], profile: Dict[str, Any]) -> Tuple[str, str, str]:
    """Return (state, customer-facing reason, confirmed-requirement label)."""
    kind = clean(requirement.get("type")).lower()
    key = clean(requirement.get("key"))
    profile_key = clean(requirement.get("profile_key")) or key
    label = clean(requirement.get("label")) or key.replace("_", " ")
    target = requirement.get("value")

    if kind == "minimum_number":
        threshold = numeric(target)
        actual = numeric(profile.get(profile_key))
        if threshold is None:
            return "conditional", f"Confirm the documented {label}.", ""
        if actual is None:
            return (
                "conditional",
                f"Confirm that you meet the {label} of at least {format_number(threshold)}.",
                "",
            )
        if actual < threshold:
            return (
                "ineligible",
                f"Requires a {label} of at least {format_number(threshold)}; the supplied value is {format_number(actual)}.",
                "",
            )
        return "eligible", "", label

    if kind == "required_boolean":
        values = profile.get("requirements")
        actual = values.get(key) if isinstance(values, dict) else None
        if actual is None:
            return "conditional", f"Confirm the required {label}.", ""
        if actual != target:
            return "ineligible", f"Does not meet the required {label}.", ""
        return "eligible", "", label

    return "conditional", f"Confirm the documented requirement: {label}.", ""


def applicable_rate(card: Dict[str, Any], categories: List[Any], weights: Dict[str, Any]) -> Tuple[Optional[float], List[str]]:
    """Return weighted supported earn rate; use default outside supported bonuses."""
    default = numeric(card.get("default_cash_back_percent"))
    category_rates = card.get("category_cash_back_percent")
    category_rates = category_rates if isinstance(category_rates, dict) else {}
    if not categories:
        return default, [] if default is not None else ["No documented applicable cash-back rate."]

    total = 0.0
    total_weight = 0.0
    failures: List[str] = []
    for raw_category in categories:
        category = clean(raw_category).lower()
        if not category:
            continue
        rate = numeric(category_rates.get(category))
        if rate is None:
            rate = default
        if rate is None:
            failures.append(f"No documented applicable cash-back rate for {category}.")
            continue
        weight = numeric(weights.get(category)) if isinstance(weights, dict) else None
        weight = weight if weight is not None and weight > 0 else 1.0
        total += rate * weight
        total_weight += weight
    if total_weight == 0:
        return None, failures or ["No usable spending category and rate were supplied."]
    return total / total_weight, failures


def evaluate_card(card: Dict[str, Any], preferences: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Apply hard constraints and classify remaining eligibility uncertainty."""
    name = clean(card.get("name")) or "Unnamed card"
    excluded: List[str] = []
    conditions: List[str] = []
    confirmed: List[str] = []
    fee = numeric(card.get("annual_fee"))
    max_fee = numeric(preferences.get("max_annual_fee"))

    # An undocumented fee cannot prove compliance with a hard fee ceiling.
    if max_fee is not None:
        if fee is None:
            excluded.append("Annual fee is not documented, so compatibility with the fee limit cannot be established.")
        elif fee > max_fee:
            excluded.append(f"Annual fee ${format_number(fee)} exceeds the maximum ${format_number(max_fee)}.")

    if card.get("invitation_only") is True:
        values = profile.get("requirements")
        invitation = values.get("invitation_only") if isinstance(values, dict) else None
        if invitation is not True:
            excluded.append("Card is invitation-only and an invitation is not confirmed.")

    requirements = card.get("requirements")
    if isinstance(requirements, list):
        for requirement in requirements:
            if not isinstance(requirement, dict):
                conditions.append("Confirm an unreadable documented requirement.")
                continue
            state, reason, label = requirement_state(requirement, profile)
            if state == "ineligible":
                excluded.append(reason)
            elif state == "conditional":
                conditions.append(reason)
            elif label:
                confirmed.append(label)

    categories = preferences.get("categories")
    categories = categories if isinstance(categories, list) else []
    weights = preferences.get("category_weights")
    weights = weights if isinstance(weights, dict) else {}
    rate, rate_errors = applicable_rate(card, categories, weights)
    excluded.extend(rate_errors)

    status = "ineligible" if excluded else ("conditional" if conditions else "eligible")
    return {
        "name": name,
        "annual_fee": fee,
        "applicable_cash_back_percent": rate,
        "rate_scope": clean(card.get("rate_scope")) or "at the documented applicable rate",
        "eligibility_status": status,
        "conditional_reasons": conditions,
        "confirmed_requirements": confirmed,
        "exclusion_reasons": excluded,
        "source_titles": card.get("source_titles") if isinstance(card.get("source_titles"), list) else [],
    }


def draft_message(candidate: Optional[Dict[str, Any]], preferences: Dict[str, Any]) -> str:
    """Draft a concise customer-facing result without claiming approval."""
    if candidate is None:
        return "No supported recommendation is available from the supplied comparable terms."

    fee = candidate["annual_fee"]
    rate = candidate["applicable_cash_back_percent"]
    name = candidate["name"]
    status = candidate["eligibility_status"]
    prefix = f"Recommendation: {name}" + (", conditionally." if status == "conditional" else ".")
    message = (
        f"{prefix} It earns {format_number(rate)}% cash back {candidate['rate_scope']} "
        f"and has a ${format_number(fee)} annual fee."
    )
    ceiling = numeric(preferences.get("max_annual_fee"))
    if ceiling is not None:
        if fee is not None and fee <= ceiling:
            message += " That meets your stated annual-fee limit."
    if candidate["confirmed_requirements"]:
        joined = ", ".join(candidate["confirmed_requirements"])
        message += f" Your confirmed {joined} satisfies that documented requirement."
    if candidate["conditional_reasons"]:
        message += " " + " ".join(candidate["conditional_reasons"])
        message += " This is conditional, not an approval; final approval is subject to underwriting."
    else:
        message += " Meeting documented requirements does not guarantee approval; final approval is subject to underwriting."
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
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({
            "errors": [str(error)],
            "ranked_candidates": [],
            "excluded": [],
            "recommendation": None,
            "customer_message": "Unable to compare the supplied terms.",
        }))
        sys.exit(1)
