#!/usr/bin/env python3
"""Evaluate normalized documented card facts without taking banking actions.

Input (stdin): JSON object documented in SKILL.md.
Output (stdout): {
  "best_documented_fit": string,
  "results": [{"name": string, "recommendable": bool, ...}]
}
Unknown source facts remain unknown; this script never determines approval.
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


def effective_foreign_fee(card, subscribed):
    if subscribed is True and card.get("foreign_fee_with_premium") is not None:
        return number(card["foreign_fee_with_premium"]), "with active premium subscription"
    if subscribed is False and card.get("foreign_fee_without_premium") is not None:
        return number(card["foreign_fee_without_premium"]), "without premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return number(card["foreign_fee_standard"]), "standard"
    if subscribed is None and (
        card.get("foreign_fee_with_premium") is not None
        or card.get("foreign_fee_without_premium") is not None
    ):
        return None, "subscription status unknown"
    return None, "not documented"


def priority_reward(card, priorities):
    rates = card.get("reward_rates") or {}
    for category in priorities:
        value = number(rates.get(category))
        if value is not None:
            return value, category, True
    # A general rate is useful fallback information but is ranked below a documented
    # category-specific rate for the customer's first stated priority.
    for category in ("all", "everyday"):
        value = number(rates.get(category))
        if value is not None:
            return value, category, False
    return None, None, False


def assess(card, customer, requirements):
    failures, unknowns, eligibility = [], [], []
    target = number(requirements.get("minimum_limit"))
    maximum = number(card.get("limit_max"))
    if target is not None:
        if maximum is None:
            unknowns.append("maximum credit limit is not documented")
        elif maximum < target:
            failures.append("documented maximum limit is below requested target")

    maximum_fee = number(requirements.get("maximum_foreign_transaction_fee"))
    foreign_fee, fee_basis = effective_foreign_fee(card, customer.get("premium_subscription"))
    if maximum_fee is not None:
        if foreign_fee is None:
            unknowns.append("foreign transaction fee cannot be confirmed")
        elif foreign_fee > maximum_fee:
            failures.append("foreign transaction fee exceeds requested maximum")

    if requirements.get("purchase_protection_required") is True:
        if number(card.get("purchase_protection_days")) is None:
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

    minimum_score = number(card.get("minimum_credit_score"))
    score = number(customer.get("credit_score"))
    if minimum_score is not None:
        if score is None:
            eligibility.append("minimum credit score cannot be assessed")
        elif score < minimum_score:
            eligibility.append("known credit score is below documented minimum")

    reward, category, category_specific = priority_reward(
        card, customer.get("spend_priorities") or []
    )
    annual_fee = number(card.get("annual_fee"))
    known_disqualification = any(
        issue.startswith("known absence") or issue.startswith("known credit")
        for issue in eligibility
    )
    recommendable = not known_disqualification and not failures

    # Ranking only orders documented candidates. It is not an approval decision.
    rank = 0
    rank += 100000 if recommendable else -100000
    rank += 10000 if not unknowns else 0
    rank += 1000 if category_specific else 0
    rank += (reward or 0) * 10
    if requirements.get("prefer_lowest_annual_fee") is True and annual_fee is not None:
        rank -= annual_fee / 1000
    return {
        "name": card.get("name", "Unnamed card"),
        "recommendable": recommendable,
        "fit_status": "matches" if not failures and not unknowns else (
            "needs_confirmation" if not failures else "does_not_match"
        ),
        "eligibility_status": "ineligible" if known_disqualification else (
            "conditional" if eligibility else "not_disqualified"
        ),
        "hard_failures": failures,
        "unknowns": unknowns,
        "eligibility_issues": eligibility,
        "priority_reward_rate": reward,
        "priority_reward_category": category,
        "priority_reward_is_category_specific": category_specific,
        "annual_fee": annual_fee,
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
        results.sort(key=lambda item: (-item["ranking_value"], item["name"]))
        print(json.dumps({"best_documented_fit": results[0]["name"], "results": results}, indent=2))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
