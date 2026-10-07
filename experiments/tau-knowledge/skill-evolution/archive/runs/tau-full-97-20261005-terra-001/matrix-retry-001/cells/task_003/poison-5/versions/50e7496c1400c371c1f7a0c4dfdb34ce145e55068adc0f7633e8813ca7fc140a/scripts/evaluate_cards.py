#!/usr/bin/env python3
"""Rank normalized, documented card facts without taking banking actions.

Read the JSON schema in SKILL.md from stdin and write one JSON assessment to
stdout. The result is informational only and does not establish eligibility,
approval, or an exact credit limit.
"""
import json
import sys


def number(value):
    """Return a finite float-like value, or None for missing/non-numeric input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def effective_foreign_fee(card, subscription):
    """Return (fee, explanation) based only on documented normalized fields."""
    if subscription is True and card.get("foreign_fee_with_premium") is not None:
        return number(card["foreign_fee_with_premium"]), "with active premium subscription"
    if subscription is False and card.get("foreign_fee_without_premium") is not None:
        return number(card["foreign_fee_without_premium"]), "without premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return number(card["foreign_fee_standard"]), "standard documented fee"
    if subscription is None and (
        card.get("foreign_fee_with_premium") is not None
        or card.get("foreign_fee_without_premium") is not None
    ):
        return None, "subscription status unknown"
    return None, "not documented"


def primary_reward(card, priorities):
    """Prefer a documented rate for the customer's stated primary category."""
    rates = card.get("reward_rates") or {}
    for category in priorities:
        rate = number(rates.get(category))
        if rate is not None:
            return rate, category, True
    for category in ("all", "everyday"):
        rate = number(rates.get(category))
        if rate is not None:
            return rate, category, False
    return None, None, False


def assess(card, customer, requirements):
    hard_failures = []
    unknowns = []
    eligibility_conditions = []

    target_limit = number(requirements.get("minimum_limit"))
    limit_max = number(card.get("limit_max"))
    if target_limit is not None:
        if limit_max is None:
            unknowns.append("maximum credit limit is not documented")
        elif limit_max < target_limit:
            hard_failures.append("documented maximum limit is below requested target")

    requested_fee = number(requirements.get("maximum_foreign_transaction_fee"))
    foreign_fee, foreign_fee_basis = effective_foreign_fee(
        card, customer.get("premium_subscription")
    )
    if requested_fee is not None:
        if foreign_fee is None:
            unknowns.append("foreign transaction fee cannot be confirmed")
        elif foreign_fee > requested_fee:
            hard_failures.append("foreign transaction fee exceeds requested maximum")

    if requirements.get("purchase_protection_required") is True:
        if number(card.get("purchase_protection_days")) is None:
            unknowns.append("purchase protection is not documented")

    if card.get("invitation_only") is True:
        if customer.get("has_invitation") is False:
            eligibility_conditions.append("required invitation is known to be absent")
        elif customer.get("has_invitation") is None:
            eligibility_conditions.append("invitation status is unknown")

    if card.get("premium_required") is True:
        if customer.get("premium_subscription") is False:
            eligibility_conditions.append("required premium subscription is known to be absent")
        elif customer.get("premium_subscription") is None:
            eligibility_conditions.append("premium-subscription status is unknown")

    minimum_score = number(card.get("minimum_credit_score"))
    customer_score = number(customer.get("credit_score"))
    if minimum_score is not None:
        if customer_score is None:
            eligibility_conditions.append("minimum credit score cannot be assessed")
        elif customer_score < minimum_score:
            eligibility_conditions.append("provided credit score is below documented minimum")

    reward_rate, reward_category, category_specific = primary_reward(
        card, customer.get("spend_priorities") or []
    )
    known_prerequisite_failure = any(
        condition.startswith("required") or condition.startswith("provided")
        for condition in eligibility_conditions
    )
    conditional_potential_fit = not known_prerequisite_failure and not hard_failures

    if known_prerequisite_failure:
        status = "not_currently_actionable"
    elif eligibility_conditions:
        status = "conditional"
    elif hard_failures:
        status = "does_not_meet_documented_hard_requirement"
    else:
        status = "not_disqualified_by_supplied_facts"

    # Ranking is a transparent advisory heuristic, not an approval decision.
    ranking_value = 1_000_000 if conditional_potential_fit else -1_000_000
    if category_specific:
        ranking_value += 2_000
    ranking_value += (reward_rate or 0) * 10
    annual_fee = number(card.get("annual_fee"))
    if requirements.get("prefer_lowest_annual_fee") is True and annual_fee is not None:
        ranking_value -= annual_fee / 1000

    return {
        "name": card.get("name", "Unnamed card"),
        "status": status,
        "conditional_potential_fit": conditional_potential_fit,
        "hard_failures": hard_failures,
        "unknowns": unknowns,
        "eligibility_conditions": eligibility_conditions,
        "foreign_transaction_fee": foreign_fee,
        "foreign_fee_basis": foreign_fee_basis,
        "primary_reward_rate": reward_rate,
        "primary_reward_category": reward_category,
        "primary_reward_is_category_specific": category_specific,
        "limit_max": limit_max,
        "annual_fee": annual_fee,
        "ranking_value": ranking_value,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        cards = payload.get("cards")
        customer = payload.get("customer")
        requirements = payload.get("requirements")
        if not isinstance(cards, list) or not cards:
            raise ValueError("cards must be a non-empty array")
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")
        if not all(isinstance(card, dict) for card in cards):
            raise ValueError("cards must contain only objects")

        results = [assess(card, customer, requirements) for card in cards]
        results.sort(key=lambda item: (-item["ranking_value"], item["name"]))
        print(json.dumps({
            "ranked_cards": results,
            "notice": (
                "Ranking is informational only and does not establish eligibility, "
                "approval, or an exact credit limit."
            ),
        }, indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
