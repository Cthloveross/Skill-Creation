#!/usr/bin/env python3
"""Render a cautious informational card-comparison draft from normalized facts.

Input: the JSON object defined in SKILL.md.
Output: {"recommendation": str, "alternatives": [str], "caveats": [str]}.
The program has no external access and performs no bank action.
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


def money(value):
    value = numeric(value)
    return "not documented" if value is None else "${:,.0f}".format(value)


def percent(value):
    value = numeric(value)
    return "not documented" if value is None else "{:g}%".format(value)


def reward_for(card, priorities):
    rates = card.get("reward_rates") or {}
    for category in list(priorities) + ["all", "everyday"]:
        value = numeric(rates.get(category))
        if value is not None:
            return value, category
    return None, "priority"


def foreign_fee_text(card, subscribed):
    if subscribed is True and card.get("foreign_fee_with_premium") is not None:
        return percent(card["foreign_fee_with_premium"]) + " with your active premium subscription"
    if subscribed is False and card.get("foreign_fee_without_premium") is not None:
        return percent(card["foreign_fee_without_premium"]) + " without a premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return percent(card["foreign_fee_standard"])
    return "not documented"


def excluded(card, customer):
    if card.get("invitation_only") is True and customer.get("has_invitation") is False:
        return True
    if card.get("premium_required") is True and customer.get("premium_subscription") is False:
        return True
    minimum = numeric(card.get("minimum_credit_score"))
    score = numeric(customer.get("credit_score"))
    return minimum is not None and score is not None and score < minimum


def score_text(card, customer):
    minimum = numeric(card.get("minimum_credit_score"))
    score = numeric(customer.get("credit_score"))
    if minimum is None:
        return "No minimum credit score is documented in the supplied terms."
    if score is None:
        return "It requires a minimum credit score of {}. Because you did not provide a credit score, eligibility cannot be confirmed.".format(int(minimum))
    if score < minimum:
        return "It requires a minimum credit score of {}, which is above the score provided.".format(int(minimum))
    return "Its documented minimum credit score is {}. Approval still requires credit review.".format(int(minimum))


def rank(card, customer, requirements):
    if excluded(card, customer):
        return -10**9
    maximum = numeric(card.get("limit_max"))
    target = numeric(requirements.get("minimum_limit"))
    value = 0
    if target is not None:
        value += 100 if maximum is not None and maximum >= target else -100
    wanted_fee = numeric(requirements.get("maximum_foreign_transaction_fee"))
    fee = None
    if customer.get("premium_subscription") is True:
        fee = numeric(card.get("foreign_fee_with_premium"))
    if fee is None:
        fee = numeric(card.get("foreign_fee_standard"))
    if wanted_fee is not None:
        value += 30 if fee is not None and fee <= wanted_fee else -30
    if requirements.get("purchase_protection_required") is True:
        value += 20 if numeric(card.get("purchase_protection_days")) is not None else -20
    reward, _ = reward_for(card, customer.get("spend_priorities") or [])
    return value + (reward or 0)


def recommendation(card, customer):
    rate, category = reward_for(card, customer.get("spend_priorities") or [])
    minimum_limit = numeric(card.get("limit_min"))
    maximum_limit = numeric(card.get("limit_max"))
    if minimum_limit is not None and maximum_limit is not None:
        limits = "Documented initial limits typically range from {} to {}".format(money(minimum_limit), money(maximum_limit))
    elif maximum_limit is not None:
        limits = "The documented possible maximum initial limit is {}".format(money(maximum_limit))
    else:
        limits = "The initial-limit range is not documented"
    days = numeric(card.get("purchase_protection_days"))
    cap = card.get("purchase_protection_cap")
    if days is None:
        protection = "purchase protection is not documented"
    else:
        cap_text = "unlimited per claim" if cap == "unlimited" else money(cap) + " per claim"
        protection = "purchase protection for {:g} days, up to {}".format(days, cap_text)
    note = card.get("reward_note") or "Eligible purchase treatment depends on the documented category and merchant coding."
    return (
        "Potential best fit: **{name}**. It earns {rate} on eligible {category} purchases. {note} "
        "Its foreign transaction fee is {foreign_fee}, it includes {protection}, and its annual fee is {annual_fee}. "
        "{limits}. {score} Approval and the exact initial limit are subject to the application, credit check, and underwriting; a requested limit is not guaranteed."
    ).format(
        name=card.get("name", "Unnamed card"), rate=percent(rate), category=category,
        note=note, foreign_fee=foreign_fee_text(card, customer), protection=protection,
        annual_fee=money(card.get("annual_fee")), limits=limits, score=score_text(card, customer),
    )


def alternative(card, customer):
    rate, category = reward_for(card, customer.get("spend_priorities") or [])
    return (
        "**{name}** is another potential option: annual fee {annual_fee}, documented possible maximum limit {limit}, "
        "and {rate} on {category} purchases. {score}"
    ).format(
        name=card.get("name", "Unnamed card"), annual_fee=money(card.get("annual_fee")),
        limit=money(card.get("limit_max")), rate=percent(rate), category=category,
        score=score_text(card, customer),
    )


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
            raise ValueError("input must be an object with a cards array")
        customer, requirements = payload.get("customer"), payload.get("requirements")
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")
        cards = [card for card in payload["cards"] if isinstance(card, dict)]
        if not cards:
            raise ValueError("cards must contain at least one object")
        cards.sort(key=lambda card: (-rank(card, customer, requirements), str(card.get("name", ""))))
        lead = cards[0]
        alternatives = [alternative(card, customer) for card in cards[1:] if not excluded(card, customer)][:2]
        caveats = []
        for card in cards:
            if card.get("invitation_only") is True and customer.get("has_invitation") is False:
                caveats.append("{} is not currently actionable because it is invitation-only and no invitation is confirmed.".format(card.get("name", "Unnamed card")))
        print(json.dumps({
            "recommendation": recommendation(lead, customer),
            "alternatives": alternatives,
            "caveats": caveats,
        }, indent=2))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
