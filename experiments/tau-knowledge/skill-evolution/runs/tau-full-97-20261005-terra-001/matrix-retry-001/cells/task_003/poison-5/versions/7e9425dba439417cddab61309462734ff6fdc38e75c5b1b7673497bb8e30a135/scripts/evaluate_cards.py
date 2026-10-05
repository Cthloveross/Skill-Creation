#!/usr/bin/env python3
"""Assess normalized, documented credit-card facts without taking banking actions.

Read one JSON object from stdin using the schema in SKILL.md. Write JSON with
ranked assessments to stdout. The result identifies documented fit and known
prerequisite failures; it never establishes approval or an exact credit limit.
"""
import json
import sys


def num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def effective_foreign_fee(card, subscribed):
    if subscribed is True and card.get("foreign_fee_with_premium") is not None:
        return num(card["foreign_fee_with_premium"]), "with active premium subscription"
    if subscribed is False and card.get("foreign_fee_without_premium") is not None:
        return num(card["foreign_fee_without_premium"]), "without premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return num(card["foreign_fee_standard"]), "standard documented fee"
    if subscribed is None and (
        card.get("foreign_fee_with_premium") is not None
        or card.get("foreign_fee_without_premium") is not None
    ):
        return None, "subscription status unknown"
    return None, "not documented"


def primary_reward(card, priorities):
    rates = card.get("reward_rates") or {}
    primary = priorities[0] if priorities else None
    if primary is not None and num(rates.get(primary)) is not None:
        return num(rates[primary]), primary, True
    for category in priorities[1:]:
        if num(rates.get(category)) is not None:
            return num(rates[category]), category, True
    for category in ("all", "everyday"):
        if num(rates.get(category)) is not None:
            return num(rates[category]), category, False
    return None, None, False


def assess(card, customer, requirements):
    failures = []
    unknowns = []
    eligibility = []

    target = num(requirements.get("minimum_limit"))
    maximum = num(card.get("limit_max"))
    if target is not None:
        if maximum is None:
            unknowns.append("maximum credit limit is not documented")
        elif maximum < target:
            failures.append("documented maximum limit is below requested target")

    wanted_fee = num(requirements.get("maximum_foreign_transaction_fee"))
    foreign_fee, foreign_fee_basis = effective_foreign_fee(
        card, customer.get("premium_subscription")
    )
    if wanted_fee is not None:
        if foreign_fee is None:
            unknowns.append("foreign transaction fee cannot be confirmed")
        elif foreign_fee > wanted_fee:
            failures.append("foreign transaction fee exceeds requested maximum")

    if requirements.get("purchase_protection_required") is True:
        if num(card.get("purchase_protection_days")) is None:
            unknowns.append("purchase protection is not documented")

    if card.get("invitation_only") is True:
        if customer.get("has_invitation") is False:
            eligibility.append("required invitation is known to be absent")
        elif customer.get("has_invitation") is None:
            eligibility.append("invitation status is unknown")

    if card.get("premium_required") is True:
        if customer.get("premium_subscription") is False:
            eligibility.append("required premium subscription is known to be absent")
        elif customer.get("premium_subscription") is None:
            eligibility.append("premium-subscription status is unknown")

    minimum_score = num(card.get("minimum_credit_score"))
    customer_score = num(customer.get("credit_score"))
    if minimum_score is not None:
        if customer_score is None:
            eligibility.append("minimum credit score cannot be assessed")
        elif customer_score < minimum_score:
            eligibility.append("provided credit score is below documented minimum")

    rate, category, category_specific = primary_reward(
        card, customer.get("spend_priorities") or []
    )
    known_disqualification = any(
        item.startswith("required") or item.startswith("provided") for item in eligibility
    )
    recommendable = not known_disqualification and not failures

    # A category-specific reward for the customer's stated main spend is deliberately
    # ranked ahead of a generic rate. This orders candidates only; it is not approval.
    rank = 0
    rank += 1_000_000 if recommendable else -1_000_000
    rank += 10_000 if not failures else 0
    rank += 2_000 if category_specific else 0
    rank += (rate or 0) * 10
    annual_fee = num(card.get("annual_fee"))
    if requirements.get("prefer_lowest_annual_fee") is True and annual_fee is not None:
        rank -= annual_fee / 1000

    return {
        "name": card.get("name", "Unnamed card"),
        "recommendable_conditional_fit": recommendable,
        "hard_fit": "matches" if not failures and not unknowns else (
            "needs_confirmation" if not failures else "does_not_match"
        ),
        "eligibility_status": "not_currently_actionable" if known_disqualification else (
            "conditional" if eligibility else "not_disqualified"
        ),
        "hard_failures": failures,
        "unknowns": unknowns,
        "eligibility_conditions": eligibility,
        "foreign_transaction_fee": foreign_fee,
        "foreign_fee_basis": foreign_fee_basis,
        "primary_reward_rate": rate,
        "primary_reward_category": category,
        "primary_reward_is_category_specific": category_specific,
        "limit_max": maximum,
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
        results = [assess(card, customer, requirements) for card in cards if isinstance(card, dict)]
        if not results:
            raise ValueError("cards must contain at least one object")
        results.sort(key=lambda item: (-item["ranking_value"], item["name"]))
        print(json.dumps({
            "best_documented_conditional_fit": results[0]["name"],
            "results": results,
            "notice": "Ranking is informational only and does not determine approval or credit limit."
        }, indent=2))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
