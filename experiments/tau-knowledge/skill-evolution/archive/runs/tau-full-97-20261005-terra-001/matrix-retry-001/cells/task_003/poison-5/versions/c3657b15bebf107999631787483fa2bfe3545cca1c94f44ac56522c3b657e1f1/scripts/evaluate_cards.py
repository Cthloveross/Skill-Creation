#!/usr/bin/env python3
"""Rank normalized documented card facts for an informational comparison.

Read one JSON object from stdin using the schema in SKILL.md and emit one JSON
object to stdout. This program does not retrieve information, establish
eligibility, perform a credit check, or take a banking action.
"""
import json
import math
import sys


def number(value):
    """Return a finite float for a numeric value, otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def effective_foreign_fee(card, premium_subscription):
    """Select only a documented fee applicable to known subscription status."""
    if premium_subscription is True and card.get("foreign_fee_with_premium") is not None:
        return number(card["foreign_fee_with_premium"]), "with active premium subscription"
    if premium_subscription is False and card.get("foreign_fee_without_premium") is not None:
        return number(card["foreign_fee_without_premium"]), "without premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return number(card["foreign_fee_standard"]), "standard documented fee"
    if card.get("foreign_fee_with_premium") is not None or card.get("foreign_fee_without_premium") is not None:
        return None, "subscription status unknown"
    return None, "not documented"


def best_reward(card, priorities):
    """Find a documented category-specific rate before a general rate."""
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
    """Classify documented fit without deciding eligibility or approval."""
    failures, unknowns, conditions = [], [], []
    target_limit = number(requirements.get("minimum_limit"))
    limit_max = number(card.get("limit_max"))
    if target_limit is not None:
        if limit_max is None:
            unknowns.append("maximum credit limit is not documented")
        elif limit_max < target_limit:
            failures.append("documented maximum limit is below requested target")

    foreign_fee, foreign_fee_basis = effective_foreign_fee(
        card, customer.get("premium_subscription")
    )
    fee_ceiling = number(requirements.get("maximum_foreign_transaction_fee"))
    if fee_ceiling is not None:
        if foreign_fee is None:
            unknowns.append("applicable foreign transaction fee cannot be confirmed")
        elif foreign_fee > fee_ceiling:
            failures.append("foreign transaction fee exceeds requested maximum")

    if requirements.get("purchase_protection_required") is True:
        if number(card.get("purchase_protection_days")) is None:
            unknowns.append("purchase protection is not documented")

    if card.get("invitation_only") is True:
        if customer.get("has_invitation") is False:
            conditions.append("required invitation is known to be absent")
        elif customer.get("has_invitation") is None:
            conditions.append("invitation status is unknown")

    if card.get("premium_required") is True:
        if customer.get("premium_subscription") is False:
            conditions.append("required premium subscription is known to be absent")
        elif customer.get("premium_subscription") is None:
            conditions.append("premium subscription status is unknown")

    minimum_score = number(card.get("minimum_credit_score"))
    customer_score = number(customer.get("credit_score"))
    if minimum_score is not None:
        if customer_score is None:
            conditions.append("minimum credit score cannot be assessed")
        elif customer_score < minimum_score:
            conditions.append("provided credit score is below documented minimum")

    known_prerequisite_failure = any(condition in {
        "required invitation is known to be absent",
        "required premium subscription is known to be absent",
        "provided credit score is below documented minimum",
    } for condition in conditions)

    reward_rate, reward_category, category_specific = best_reward(
        card, customer.get("spend_priorities") or []
    )
    if known_prerequisite_failure:
        status = "not_currently_actionable"
    elif failures:
        status = "does_not_meet_documented_hard_requirement"
    elif conditions or unknowns:
        status = "conditional"
    else:
        status = "not_disqualified_by_supplied_facts"

    # Ordering heuristic only; it never implies approval or eligibility.
    score = 0
    if not known_prerequisite_failure and not failures:
        score += 1_000_000
    if category_specific:
        score += 2_000
    score += (reward_rate or 0) * 10
    annual_fee = number(card.get("annual_fee"))
    if requirements.get("prefer_lowest_annual_fee") is True and annual_fee is not None:
        score -= annual_fee / 1000

    return {
        "name": card.get("name", "Unnamed card"),
        "status": status,
        "conditional_potential_fit": not known_prerequisite_failure and not failures,
        "hard_failures": failures,
        "unknowns": unknowns,
        "eligibility_conditions": conditions,
        "foreign_transaction_fee": foreign_fee,
        "foreign_fee_basis": foreign_fee_basis,
        "primary_reward_rate": reward_rate,
        "primary_reward_category": reward_category,
        "primary_reward_is_category_specific": category_specific,
        "limit_max": limit_max,
        "annual_fee": annual_fee,
        "ranking_value": score,
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

        ranked = [assess(card, customer, requirements) for card in cards]
        ranked.sort(key=lambda item: (-item["ranking_value"], item["name"]))
        print(json.dumps({
            "ranked_cards": ranked,
            "notice": (
                "Informational ranking only; it does not establish eligibility, "
                "approval, or an exact credit limit."
            ),
        }, indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
