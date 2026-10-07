#!/usr/bin/env python3
"""Evaluate documented card facts against customer requirements.

Input: JSON object with the schema in SKILL.md.
Output: JSON object with a sorted `results` list. This program has no side effects.
"""
import json
import sys


def as_number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fee_for_customer(card, subscribed):
    if subscribed is True and card.get("foreign_fee_with_premium") is not None:
        return as_number(card.get("foreign_fee_with_premium")), "with active premium subscription"
    if subscribed is False and card.get("foreign_fee_without_premium") is not None:
        return as_number(card.get("foreign_fee_without_premium")), "without premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return as_number(card.get("foreign_fee_standard")), "standard"
    if subscribed is None and (card.get("foreign_fee_with_premium") is not None or card.get("foreign_fee_without_premium") is not None):
        return None, "subscription status unknown"
    return None, "not documented"


def best_reward(card, priorities):
    rates = card.get("reward_rates") or {}
    choices = []
    for priority in priorities:
        rate = as_number(rates.get(priority))
        if rate is not None:
            choices.append((rate, priority))
    for fallback in ("all", "everyday"):
        rate = as_number(rates.get(fallback))
        if rate is not None:
            choices.append((rate, fallback))
    return max(choices, default=(None, None), key=lambda item: item[0] if item[0] is not None else -1)


def evaluate(card, customer, requirements):
    hard_failures, unknowns, eligibility_issues = [], [], []
    max_limit = as_number(card.get("limit_max"))
    wanted_limit = as_number(requirements.get("minimum_limit"))
    if wanted_limit is not None:
        if max_limit is None:
            unknowns.append("maximum credit limit is not documented")
        elif max_limit < wanted_limit:
            hard_failures.append("documented maximum limit is below requested target")

    wanted_fee = as_number(requirements.get("maximum_foreign_transaction_fee"))
    foreign_fee, fee_basis = fee_for_customer(card, customer.get("premium_subscription"))
    if wanted_fee is not None:
        if foreign_fee is None:
            unknowns.append("foreign transaction fee cannot be confirmed")
        elif foreign_fee > wanted_fee:
            hard_failures.append("foreign transaction fee exceeds requested maximum")

    if requirements.get("purchase_protection_required") is True:
        days = as_number(card.get("purchase_protection_days"))
        if days is None:
            unknowns.append("purchase protection is not documented")

    if card.get("invitation_only") is True:
        if customer.get("has_invitation") is False:
            eligibility_issues.append("invitation-only card with no confirmed invitation")
        elif customer.get("has_invitation") is None:
            eligibility_issues.append("invitation status unknown")
    if card.get("premium_required") is True:
        if customer.get("premium_subscription") is False:
            eligibility_issues.append("required premium subscription absent")
        elif customer.get("premium_subscription") is None:
            eligibility_issues.append("premium-subscription status unknown")
    minimum_score = as_number(card.get("minimum_credit_score"))
    score = as_number(customer.get("credit_score"))
    if minimum_score is not None:
        if score is None:
            eligibility_issues.append("minimum credit score cannot be assessed")
        elif score < minimum_score:
            eligibility_issues.append("known credit score is below documented minimum")

    rate, category = best_reward(card, customer.get("spend_priorities") or [])
    ineligible = any(issue.startswith("invitation-only") or issue.startswith("required premium") or issue.startswith("known credit") for issue in eligibility_issues)
    match = "does_not_match" if hard_failures else ("needs_confirmation" if unknowns else "matches")
    eligibility = "ineligible" if ineligible else ("conditional" if eligibility_issues else "eligible")
    utility = {"eligible": 2, "conditional": 1, "ineligible": 0}[eligibility] * 10000
    utility += {"matches": 2, "needs_confirmation": 1, "does_not_match": 0}[match] * 1000
    utility += rate or 0
    return {
        "name": card.get("name", "Unnamed card"),
        "match_status": match,
        "eligibility_status": eligibility,
        "hard_failures": hard_failures,
        "unknowns": unknowns,
        "eligibility_issues": eligibility_issues,
        "priority_reward_rate": rate,
        "priority_reward_category": category,
        "foreign_transaction_fee": foreign_fee,
        "foreign_fee_basis": fee_basis,
        "limit_max": max_limit,
        "ordering_utility": utility,
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
        results = [evaluate(card, customer, requirements) for card in cards if isinstance(card, dict)]
        if not results:
            raise ValueError("cards must contain an object")
        results.sort(key=lambda item: (-item["ordering_utility"], item["name"]))
        print(json.dumps({"best_documented_fit": results[0]["name"], "results": results}, indent=2))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
