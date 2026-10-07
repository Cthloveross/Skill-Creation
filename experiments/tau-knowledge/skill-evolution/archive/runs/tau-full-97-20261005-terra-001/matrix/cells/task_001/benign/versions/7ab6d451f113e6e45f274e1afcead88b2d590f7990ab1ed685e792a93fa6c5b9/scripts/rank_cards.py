#!/usr/bin/env python3
"""Rank documented cash-back cards against supplied preferences.

Reads one JSON object from stdin and writes one JSON object to stdout. It evaluates
only supplied facts and does not access accounts, apply for products, or perform
underwriting.
"""

import json
import math
import sys


def clean_text(value):
    return value.strip() if isinstance(value, str) else ""


def as_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def boolean_requirement(profile, key):
    requirements = profile.get("requirements", {})
    if not isinstance(requirements, dict):
        return None
    value = requirements.get(key)
    return value if isinstance(value, bool) else None


def applicable_rate(card, preferences):
    default_rate = as_number(card.get("default_cash_back_percent"))
    bonuses = card.get("category_cash_back_percent", {})
    bonuses = bonuses if isinstance(bonuses, dict) else {}
    categories = preferences.get("categories", [])
    weights = preferences.get("category_weights", {})
    categories = categories if isinstance(categories, list) else []
    weights = weights if isinstance(weights, dict) else {}

    if not categories:
        if default_rate is None:
            return None, ["No documented default cash-back rate."]
        return default_rate, []

    total = 0.0
    total_weight = 0.0
    errors = []
    for raw_category in categories:
        category = clean_text(raw_category).lower()
        if not category:
            continue
        rate = as_number(bonuses.get(category))
        if rate is None:
            rate = default_rate
        if rate is None:
            errors.append("No documented applicable cash-back rate for " + category + ".")
            continue
        weight = as_number(weights.get(category))
        weight = weight if weight is not None and weight > 0 else 1.0
        total += rate * weight
        total_weight += weight

    if total_weight == 0:
        return None, errors or ["No usable spending categories were supplied."]
    return total / total_weight, errors


def assess_requirement(requirement, profile):
    kind = clean_text(requirement.get("type")).lower()
    label = clean_text(requirement.get("label")) or "documented requirement"

    if kind == "minimum_number":
        threshold = as_number(requirement.get("value"))
        field = clean_text(requirement.get("profile_key")) or "credit_score"
        actual = as_number(profile.get(field))
        if threshold is None:
            return "conditional", "Confirm the " + label + "."
        if actual is None:
            return "conditional", "Confirm that you meet the " + label + " of at least " + format(threshold, "g") + "."
        if actual < threshold:
            return "ineligible", "Requires " + label + " of at least " + format(threshold, "g") + "."
        return "eligible", ""

    if kind == "required_boolean":
        key = clean_text(requirement.get("key"))
        expected = requirement.get("value")
        actual = boolean_requirement(profile, key)
        if not isinstance(expected, bool) or actual is None:
            return "conditional", "Confirm the required " + label + " is active and qualifying."
        if actual != expected:
            return "ineligible", "Does not currently meet the required " + label + "."
        return "eligible", ""

    return "conditional", "Confirm the " + label + "."


def assess_card(card, preferences, profile):
    exclusions = []
    conditions = []
    fee = as_number(card.get("annual_fee"))
    ceiling = as_number(preferences.get("max_annual_fee"))

    if ceiling is not None:
        if fee is None:
            exclusions.append("Permanent annual fee is not documented.")
        elif fee > ceiling:
            exclusions.append("Permanent annual fee exceeds the customer's limit.")

    if card.get("invitation_only") is True and profile.get("invitation_confirmed") is not True:
        exclusions.append("Card is invitation-only and no invitation is confirmed.")

    requirements = card.get("requirements", [])
    requirements = requirements if isinstance(requirements, list) else []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            conditions.append("Confirm an unreadable documented requirement.")
            continue
        state, message = assess_requirement(requirement, profile)
        if state == "ineligible":
            exclusions.append(message)
        elif state == "conditional":
            conditions.append(message)

    rate, rate_errors = applicable_rate(card, preferences)
    exclusions.extend(rate_errors)
    status = "ineligible" if exclusions else ("conditional" if conditions else "eligible")
    return {
        "name": clean_text(card.get("name")),
        "annual_fee": fee,
        "applicable_cash_back_percent": rate,
        "rate_scope": clean_text(card.get("rate_scope")) or "at the documented applicable rate",
        "status": status,
        "conditions": conditions,
        "exclusion_reasons": exclusions,
    }


def rank(payload):
    errors = []
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

    evaluated = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append("cards[%d] must be an object." % index)
        elif not clean_text(card.get("name")):
            errors.append("cards[%d] is missing a name." % index)
        else:
            evaluated.append(assess_card(card, preferences, profile))

    candidates = [item for item in evaluated if item["status"] != "ineligible"]
    excluded = [item for item in evaluated if item["status"] == "ineligible"]
    priority = {"eligible": 0, "conditional": 1}
    candidates.sort(
        key=lambda item: (
            -(item["applicable_cash_back_percent"] if item["applicable_cash_back_percent"] is not None else -1),
            priority[item["status"]],
            item["annual_fee"] if item["annual_fee"] is not None else float("inf"),
            item["name"].lower(),
        )
    )
    return {
        "errors": errors,
        "ranked_candidates": candidates,
        "excluded": excluded,
        "recommendation": candidates[0] if candidates else None,
        "interpretation": "A conditional recommendation requires confirmation of every listed condition and is not an approval decision.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(rank(payload), ensure_ascii=False, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"errors": [str(error)], "ranked_candidates": [], "excluded": [], "recommendation": None}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
