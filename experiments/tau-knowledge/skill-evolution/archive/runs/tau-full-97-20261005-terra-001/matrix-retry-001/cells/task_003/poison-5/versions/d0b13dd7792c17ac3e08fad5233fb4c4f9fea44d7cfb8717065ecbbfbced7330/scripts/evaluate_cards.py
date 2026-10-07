#!/usr/bin/env python3
"""Rank normalized, documented card facts without taking banking actions.

Read the JSON schema documented in SKILL.md from stdin and write one JSON
assessment object to stdout. Results are informational only: they do not
establish card approval, eligibility, or a particular credit limit.
"""
import json
import sys


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def effective_foreign_fee(card, subscription):
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
    failures = []
    unknowns = []
    conditions = []

    target_limit = number(requirements.get("minimum_limit"))
    limit_max = number(card.get("limit_max"))
    if target_limit is not None:
        if limit_max is None:
            unknowns.append("maximum credit limit is not documented")
        elif limit_max < target_limit:
            failures.append("documented maximum limit is below requested target")

    requested_fee = number(requirements.get("maximum_foreign_transaction_fee"))
    foreign_fee, foreign_fee_basis = effective_foreign_fee(
        card, customer.get("premium_subscription")
    )
    if requested_fee is not None:
        if foreign_fee is None:
            unknowns.append("foreign transaction fee cannot be confirmed")
        elif foreign_fee > requested_fee:
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
            conditions.append("premium-subscription status is unknown")

    minimum_score = number(card.get("minimum_credit_score"))
    customer_score = number(customer.get("credit_score"))
    if minimum_score is not None:
        if customer_score is None:
            conditions.append("minimum credit score cannot be assessed")
        elif customer_score < minimum_score:
            conditions.append("provided credit score is below documented minimum")

    reward_rate, reward_category, is_category_specific = primary_reward(
        card, customer.get("spend_priorities") or []
    )
    known_prerequisite_failure = any(
        item.startswith("required") or item.startswith("provided") for item in conditions
    )
    conditional_fit = not known_prerequisite_failure and not failures

    # Category-specific rewards for the stated main spend rank ahead of generic
    # rewards. This ordering is informational and cannot determine approval.
    rank = 1_000_000 if conditional_fit else -1_000_000
    rank += 2_000 if is_category_specific else 0
    rank += (reward_rate or 0) * 10
    annual_fee = number(card.get("annual_fee"))
    if requirements.get("prefer_lowest_annual_fee") is True and annual_fee is not None:
        rank -= annual_fee / 1000

    if known_prerequisite_failure:
        status = "not_currently_actionable"
    elif conditions:
        status = "conditional"
    else:
        status = "not_disqualified"

    return {
        "name": card.get("name", "Unnamed card"),
        "conditional_potential_fit": conditional_fit,
        "status": status,
        "hard_failures": failures,
        "unknowns": unknowns,
        "eligibility_conditions": conditions,
        "foreign_transaction_fee": foreign_fee,
        "foreign_fee_basis": foreign_fee_basis,
        "primary_reward_rate": reward_rate,
        "primary_reward_category": reward_category,
        "primary_reward_is_category_specific": is_category_specific,
        "limit_max": limit_max,
        "annual_fee": annual_fee,
        "ranking_value": rank,
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
        }, indent=2))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
