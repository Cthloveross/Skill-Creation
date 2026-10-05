#!/usr/bin/env python3
"""Rank documented cash-back cards under supplied customer constraints.

Reads one JSON object from stdin and writes one JSON object to stdout. The script
only evaluates the facts passed to it; it does not access accounts, apply for a
product, or make an underwriting determination.
"""

import json
import math
import sys


def text(value):
    return value.strip() if isinstance(value, str) else ""


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def profile_bool(profile, key):
    requirements = profile.get("requirements", {})
    if not isinstance(requirements, dict):
        return None
    value = requirements.get(key)
    return value if isinstance(value, bool) else None


def rate_for(card, preferences):
    default = number(card.get("default_cash_back_percent"))
    bonuses = card.get("category_cash_back_percent", {})
    bonuses = bonuses if isinstance(bonuses, dict) else {}
    categories = preferences.get("categories", [])
    weights = preferences.get("category_weights", {})
    categories = categories if isinstance(categories, list) else []
    weights = weights if isinstance(weights, dict) else {}
    if not categories:
        return default, [] if default is not None else ["No documented default cash-back rate."]

    total, weight_total, errors = 0.0, 0.0, []
    for raw_category in categories:
        category = text(raw_category).lower()
        if not category:
            continue
        rate = number(bonuses.get(category))
        if rate is None:
            rate = default
        if rate is None:
            errors.append("No documented applicable cash-back rate for " + category + ".")
            continue
        weight = number(weights.get(category))
        weight = weight if weight is not None and weight > 0 else 1.0
        total += rate * weight
        weight_total += weight
    if weight_total == 0:
        return None, errors or ["No usable spending categories were supplied."]
    return total / weight_total, errors


def check_requirement(requirement, profile):
    kind = text(requirement.get("type")).lower()
    label = text(requirement.get("label")) or "documented requirement"
    if kind == "minimum_number":
        threshold = number(requirement.get("value"))
        actual = number(profile.get(text(requirement.get("profile_key")) or "credit_score"))
        if threshold is None:
            return "conditional", "Confirm the " + label + "."
        if actual is None:
            return "conditional", "Confirm that you meet the " + label + " of at least " + format(threshold, "g") + "."
        if actual < threshold:
            return "ineligible", "Requires " + label + " of at least " + format(threshold, "g") + "."
        return "eligible", ""
    if kind == "required_boolean":
        key = text(requirement.get("key"))
        target = requirement.get("value")
        actual = profile_bool(profile, key)
        if not isinstance(target, bool) or actual is None:
            return "conditional", "Confirm the required " + label + " is active and qualifies."
        if actual != target:
            return "ineligible", "Does not currently meet the required " + label + "."
        return "eligible", ""
    return "conditional", "Confirm the " + label + "."


def evaluate(card, preferences, profile):
    excluded, conditions = [], []
    name = text(card.get("name")) or "Unnamed card"
    fee = number(card.get("annual_fee"))
    ceiling = number(preferences.get("max_annual_fee"))
    if ceiling is not None:
        if fee is None:
            excluded.append("Permanent annual fee is not documented.")
        elif fee > ceiling:
            excluded.append("Permanent annual fee exceeds the customer's limit.")
    if card.get("invitation_only") is True and profile.get("invitation_confirmed") is not True:
        excluded.append("Card is invitation-only and no invitation is confirmed.")

    requirements = card.get("requirements", [])
    if not isinstance(requirements, list):
        requirements = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            conditions.append("Confirm an unreadable documented requirement.")
            continue
        state, reason = check_requirement(requirement, profile)
        if state == "ineligible":
            excluded.append(reason)
        elif state == "conditional":
            conditions.append(reason)

    rate, rate_errors = rate_for(card, preferences)
    excluded.extend(rate_errors)
    status = "ineligible" if excluded else ("conditional" if conditions else "eligible")
    return {
        "name": name,
        "annual_fee": fee,
        "applicable_cash_back_percent": rate,
        "rate_scope": text(card.get("rate_scope")) or "at the documented applicable rate",
        "status": status,
        "conditions": conditions,
        "exclusion_reasons": excluded,
    }


def main(payload):
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
        elif not text(card.get("name")):
            errors.append("cards[%d] is missing a name." % index)
        else:
            evaluated.append(evaluate(card, preferences, profile))

    candidates = [item for item in evaluated if item["status"] != "ineligible"]
    excluded = [item for item in evaluated if item["status"] == "ineligible"]
    status_order = {"eligible": 0, "conditional": 1}
    candidates.sort(key=lambda item: (
        -(item["applicable_cash_back_percent"] if item["applicable_cash_back_percent"] is not None else -1),
        status_order[item["status"]],
        item["annual_fee"] if item["annual_fee"] is not None else float("inf"),
        item["name"].lower(),
    ))
    return {
        "errors": errors,
        "ranked_candidates": candidates,
        "excluded": excluded,
        "recommendation": candidates[0] if candidates else None,
        "interpretation": "A conditional recommendation requires confirmation of every listed condition and is not an approval decision.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"errors": [str(error)], "ranked_candidates": [], "excluded": [], "recommendation": None}, sort_keys=True))
        sys.exit(1)
