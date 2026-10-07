#!/usr/bin/env python3
"""Rank checking/savings combinations from structured public product facts.

Reads one JSON object from stdin and writes one JSON object to stdout.  APY values are
percentage points, e.g. 3.0 represents 3.0%, not 0.03.
"""
import json
import sys


def number(value, label, errors, default=0.0):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{label} must be numeric")
        return default
    return float(value)


def required_present(option, required):
    features = option.get("features", [])
    if not isinstance(features, list):
        return False, ["features is not a list"]
    missing = [feature for feature in required if feature not in features]
    return not missing, missing


def applicable_tier(tiers, balance, errors, name):
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"{name}: tiers must be a nonempty list")
        return None
    valid = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            errors.append(f"{name}: tier {index} must be an object")
            continue
        minimum = number(tier.get("min_balance"), f"{name}: tier {index} min_balance", errors)
        apy = number(tier.get("apy_pct"), f"{name}: tier {index} apy_pct", errors)
        if minimum <= balance:
            valid.append((minimum, apy))
    if not valid:
        return None
    return max(valid, key=lambda pair: pair[0])


def main(data):
    errors = []
    balance = number(data.get("balance"), "balance", errors, default=-1.0)
    if balance < 0:
        errors.append("balance must be nonnegative")

    required_checking = data.get("required_checking_features", [])
    required_savings = data.get("required_savings_features", [])
    checking_options = data.get("checking_options", [])
    savings_options = data.get("savings_options", [])
    if not all(isinstance(x, list) for x in (required_checking, required_savings, checking_options, savings_options)):
        errors.append("required feature lists and option lists must be arrays")
        return {"recommendations": [], "excluded": [], "errors": errors}

    card_bonuses = data.get("credit_card_bonuses", [])
    if not isinstance(card_bonuses, list):
        errors.append("credit_card_bonuses must be an array")
        card_bonuses = []
    numeric_cards = [number(v, "credit_card_bonuses item", errors) for v in card_bonuses]
    highest_card_bonus = max(numeric_cards, default=0.0)
    global_relationship = number(data.get("relationship_bonus_pct"), "relationship_bonus_pct", errors)
    global_direct_deposit = number(data.get("direct_deposit_bonus_pct"), "direct_deposit_bonus_pct", errors)

    recommendations = []
    excluded = []
    for savings in savings_options:
        if not isinstance(savings, dict) or not isinstance(savings.get("name"), str):
            errors.append("each savings option requires a string name")
            continue
        savings_name = savings["name"]
        savings_ok, savings_missing = required_present(savings, required_savings)
        opening_min = number(savings.get("opening_minimum"), f"{savings_name}: opening_minimum", errors)
        ongoing_min = number(savings.get("ongoing_minimum"), f"{savings_name}: ongoing_minimum", errors)
        tier = applicable_tier(savings.get("tiers"), balance, errors, savings_name)
        if not savings_ok:
            excluded.append({"savings": savings_name, "reason": "missing required savings features", "missing": savings_missing})
            continue
        if balance < opening_min or balance < ongoing_min:
            excluded.append({"savings": savings_name, "reason": "balance does not meet stated opening or ongoing minimum"})
            continue
        if tier is None:
            excluded.append({"savings": savings_name, "reason": "no APY tier applies at supplied balance"})
            continue
        tier_min, base_apy = tier
        for checking in checking_options:
            if not isinstance(checking, dict) or not isinstance(checking.get("name"), str):
                errors.append("each checking option requires a string name")
                continue
            checking_name = checking["name"]
            checking_ok, checking_missing = required_present(checking, required_checking)
            if not checking_ok:
                excluded.append({"checking": checking_name, "savings": savings_name, "reason": "missing required checking features", "missing": checking_missing})
                continue
            boosts = checking.get("boosts", {})
            if not isinstance(boosts, dict):
                errors.append(f"{checking_name}: boosts must be an object")
                boosts = {}
            checking_boost = number(boosts.get(savings_name), f"{checking_name}: boost for {savings_name}", errors)
            relationship = number(savings.get("relationship_bonus_pct", global_relationship), f"{savings_name}: relationship_bonus_pct", errors)
            direct_deposit = number(savings.get("direct_deposit_bonus_pct", global_direct_deposit), f"{savings_name}: direct_deposit_bonus_pct", errors)
            components = {
                "base_apy_pct": base_apy,
                "checking_boost_pct": checking_boost,
                "highest_credit_card_bonus_pct": highest_card_bonus,
                "relationship_bonus_pct": relationship,
                "direct_deposit_bonus_pct": direct_deposit,
            }
            effective = sum(components.values())
            recommendations.append({
                "checking": checking_name,
                "savings": savings_name,
                "balance": balance,
                "tier_minimum_balance": tier_min,
                "effective_apy_pct": round(effective, 6),
                "components": components,
                "assumptions": [
                    "Only the highest supplied credit-card bonus is included.",
                    "This calculation assumes every supplied bonus is currently eligible and active.",
                    "A checking boost is included only when supplied for this exact savings option."
                ]
            })
    recommendations.sort(key=lambda item: item["effective_apy_pct"], reverse=True)
    return {"recommendations": recommendations, "excluded": excluded, "errors": errors}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"recommendations": [], "excluded": [], "errors": [str(exc)]}, sort_keys=True))
