#!/usr/bin/env python3
"""Create an advisory card-comparison response skeleton from documented facts.

Input: JSON object following the SKILL.md schema.
Output: JSON with `recommendation`, `alternatives`, and `caveats` strings.
No bank action is performed. The caller must verify extracted facts against source documents.
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


def money(value):
    value = number(value)
    if value is None:
        return "not documented"
    return "${:,.0f}".format(value)


def pct(value):
    value = number(value)
    if value is None:
        return "not documented"
    return "{:g}%".format(value)


def foreign_fee(card, subscribed):
    if subscribed is True and card.get("foreign_fee_with_premium") is not None:
        return pct(card["foreign_fee_with_premium"]) + " with your active premium subscription"
    if subscribed is False and card.get("foreign_fee_without_premium") is not None:
        return pct(card["foreign_fee_without_premium"]) + " without a premium subscription"
    if card.get("foreign_fee_standard") is not None:
        return pct(card["foreign_fee_standard"])
    return "not documented"


def reward(card, priorities):
    rates = card.get("reward_rates") or {}
    for category in priorities:
        if number(rates.get(category)) is not None:
            return pct(rates[category]), category
    for category in ("all", "everyday"):
        if number(rates.get(category)) is not None:
            return pct(rates[category]), category
    return "not documented", "priority purchases"


def score_state(card, customer):
    minimum = number(card.get("minimum_credit_score"))
    actual = number(customer.get("credit_score"))
    if minimum is None:
        return "No minimum credit score is documented in the supplied terms."
    if actual is None:
        return "It requires a minimum credit score of {}. Because no score was provided, eligibility cannot be confirmed.".format(int(minimum))
    if actual < minimum:
        return "It requires a minimum credit score of {}, which is above the score provided.".format(int(minimum))
    return "Its documented minimum credit score is {}.".format(int(minimum))


def eligible_for_consideration(card, customer):
    if card.get("invitation_only") is True and customer.get("has_invitation") is False:
        return False
    if card.get("premium_required") is True and customer.get("premium_subscription") is False:
        return False
    minimum = number(card.get("minimum_credit_score"))
    actual = number(customer.get("credit_score"))
    return not (minimum is not None and actual is not None and actual < minimum)


def rank(card, customer, requirements):
    if not eligible_for_consideration(card, customer):
        return -1e9
    score = 0.0
    maximum = number(card.get("limit_max"))
    target = number(requirements.get("minimum_limit"))
    if target is not None and maximum is not None:
        score += 100 if maximum >= target else -100
    fee = None
    if customer.get("premium_subscription") is True:
        fee = number(card.get("foreign_fee_with_premium"))
    if fee is None:
        fee = number(card.get("foreign_fee_standard"))
    wanted_fee = number(requirements.get("maximum_foreign_transaction_fee"))
    if wanted_fee is not None and fee is not None:
        score += 30 if fee <= wanted_fee else -30
    if requirements.get("purchase_protection_required") and number(card.get("purchase_protection_days")) is not None:
        score += 20
    rate, _ = reward(card, customer.get("spend_priorities") or [])
    score += number(rate.rstrip("%")) or 0
    return score


def lead_text(card, customer, requirements):
    rate, category = reward(card, customer.get("spend_priorities") or [])
    limit_min, limit_max = number(card.get("limit_min")), number(card.get("limit_max"))
    if limit_min is not None and limit_max is not None:
        limit_text = "documented initial limits typically range from {} to {}".format(money(limit_min), money(limit_max))
    elif limit_max is not None:
        limit_text = "the documented maximum possible limit is {}".format(money(limit_max))
    else:
        limit_text = "the limit range is not documented"
    protection_days = number(card.get("purchase_protection_days"))
    cap = card.get("purchase_protection_cap")
    protection = "not documented"
    if protection_days is not None:
        cap_text = "unlimited per claim" if cap == "unlimited" else money(cap) + " per claim"
        protection = "purchase protection for {:g} days, up to {}".format(protection_days, cap_text)
    annual_fee = money(card.get("annual_fee"))
    note = card.get("reward_note") or "Eligible purchases are determined by the merchant category."
    return (
        "**Potential best fit: {name}.** For your {category}-focused spending, it earns {rate} on eligible {category} purchases. "
        "It has a {foreign_fee} foreign transaction fee, {protection}, and {limit_text}. "
        "The documented annual fee is {annual_fee}. {note} "
        "{score_state} Approval and your exact initial limit are subject to the application, credit check, and underwriting, so a requested limit is not guaranteed."
    ).format(name=card.get("name", "Unnamed card"), category=category, rate=rate,
             foreign_fee=foreign_fee(card, customer.get("premium_subscription")), protection=protection,
             limit_text=limit_text, annual_fee=annual_fee, note=note, score_state=score_state(card, customer))


def alternative_text(card, customer):
    rate, category = reward(card, customer.get("spend_priorities") or [])
    maximum = number(card.get("limit_max"))
    limit = money(maximum) if maximum is not None else "an undocumented maximum"
    fee = money(card.get("annual_fee"))
    return "{} is an alternative: annual fee {}, possible maximum limit {}, and {} on {} purchases. {}".format(
        card.get("name", "Unnamed card"), fee, limit, rate, category, score_state(card, customer))


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
            raise ValueError("input must be an object with a cards array")
        customer = payload.get("customer")
        requirements = payload.get("requirements")
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")
        cards = [card for card in payload["cards"] if isinstance(card, dict)]
        if not cards:
            raise ValueError("cards must contain at least one object")
        cards.sort(key=lambda card: (-rank(card, customer, requirements), str(card.get("name", ""))))
        lead = cards[0]
        alternatives = [alternative_text(card, customer) for card in cards[1:]
                        if eligible_for_consideration(card, customer)][:2]
        excluded = [card.get("name", "Unnamed card") for card in cards
                    if card.get("invitation_only") is True and customer.get("has_invitation") is False]
        caveats = []
        if excluded:
            caveats.append("Not currently actionable: {} is invitation-only and no invitation is confirmed.".format(", ".join(excluded)))
        print(json.dumps({
            "recommendation": lead_text(lead, customer, requirements),
            "alternatives": alternatives,
            "caveats": caveats,
        }, indent=2))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
