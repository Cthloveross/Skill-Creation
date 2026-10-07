#!/usr/bin/env python3
"""Evaluate normalized, documented card facts without performing bank actions.

Input: the JSON object defined in SKILL.md.
Output: {"best_documented_fit": str, "results": [object, ...]}.
"""
import json
import sys


def numeric(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def effective_foreign_fee(card, subscribed):
    if subscribed is True and card.get("foreign_fee_with_premium") is not None:
        return numeric(card["foreign_fee_with_premium"]), "with active premium subscription"
    if subscribed is False and card.get("foreign_fee_without_premium") is not None:
        return numeric(card["foreign_fee_without_premium"]), "without premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return numeric(card["foreign_fee_standard"]), "standard"
    if subscribed is None and (
        card.get("foreign_fee_with_premium") is not None
        or card.get("foreign_fee_without_premium") is not None
    ):
        return None, "subscription status unknown"
    return None, "not documented"


def priority_reward(card, priorities):
    rates = card.get("reward_rates") or {}
    for category in priorities:
        rate = numeric(rates.get(category))
        if rate is not None:
            return rate, category
    for category in ("all", "everyday"):
        rate = numeric(rates.get(category))
        if rate is not None:
            return rate, category
    return None, None


def assess(card, customer, requirements):
    failures, unknowns, eligibility = [], [], []
    target = numeric(requirements.get("minimum_limit"))
    maximum = numeric(card.get("limit_max"))
    if target is not None:
        if maximum is None:
            unknowns.append("maximum credit limit is not documented")
        elif maximum < target:
            failures.append("documented maximum limit is below requested target")

    required_fee = numeric(requirements.get("maximum_foreign_transaction_fee"))
    foreign_fee, fee_basis = effective_foreign_fee(card, customer.get("premium_subscription"))
    if required_fee is not None:
        if foreign_fee is None:
            unknowns.append("foreign transaction fee cannot be confirmed")
        elif foreign_fee > required_fee:
            failures.append("foreign transaction fee exceeds requested maximum")

    if requirements.get("purchase_protection_required") is True:
        if numeric(card.get("purchase_protection_days")) is None:
            unknowns.append("purchase protection is not documented")

    if card.get("invitation_only") is True:
        if customer.get("has_invitation") is False:
            eligibility.append("known absence of required invitation")
        elif customer.get("has_invitation") is None:
            eligibility.append("invitation status unknown")
    if card.get("premium_required") is True:
        if customer.get("premium_subscription") is False:
            eligibility.append("known absence of required premium subscription")
        elif customer.get("premium_subscription") is None:
            eligibility.append("premium-subscription status unknown")

    minimum_score = numeric(card.get("minimum_credit_score"))
    customer_score = numeric(customer.get("credit_score"))
    if minimum_score is not None:
        if customer_score is None:
            eligibility.append("minimum credit score cannot be assessed")
        elif customer_score < minimum_score:
            eligibility.append("known credit score is below documented minimum")

    reward, reward_category = priority_reward(card, customer.get("spend_priorities") or [])
    ineligible = any(item.startswith("known absence") or item.startswith("known credit") for item in eligibility)
    fit = "does_not_match" if failures else ("needs_confirmation" if unknowns else "matches")
    eligibility_status = "ineligible" if ineligible else ("conditional" if eligibility else "not_disqualified")
    # Hard failures and known disqualification dominate ranking; then favor priority rewards.
    rank = (0 if ineligible else 100000) + (0 if failures else 10000) + (0 if unknowns else 1000) + (reward or 0)
    return {
        "name": card.get("name", "Unnamed card"),
        "fit_status": fit,
        "eligibility_status": eligibility_status,
        "hard_failures": failures,
        "unknowns": unknowns,
        "eligibility_issues": eligibility,
        "priority_reward_rate": reward,
        "priority_reward_category": reward_category,
        "foreign_transaction_fee": foreign_fee,
        "foreign_fee_basis": fee_basis,
        "limit_max": maximum,
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
        results.sort(key=lambda result: (-result["ranking_value"], result["name"]))
        print(json.dumps({"best_documented_fit": results[0]["name"], "results": results}, indent=2))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
