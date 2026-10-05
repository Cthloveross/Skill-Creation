#!/usr/bin/env python3
"""Evaluate documented card records against customer requirements.

Input: one JSON object following the schema in SKILL.md.
Output: JSON with sorted card results, no side effects and no external dependencies.
"""
import json
import sys
from datetime import date


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def iso_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def field(card, key, default=None):
    value = card.get(key, default)
    return value if value is not None else default


def limit_max(card):
    limits = field(card, "limit_range", {})
    if isinstance(limits, dict):
        return number(limits.get("max"))
    if isinstance(limits, list) and len(limits) > 1:
        return number(limits[1])
    return number(card.get("limit_max"))


def foreign_fee(card, premium_subscription):
    fee = field(card, "foreign_transaction_fee", None)
    if isinstance(fee, dict):
        if premium_subscription is True and fee.get("with_premium") is not None:
            return number(fee.get("with_premium")), "with_premium"
        if premium_subscription is False and fee.get("without_premium") is not None:
            return number(fee.get("without_premium")), "without_premium"
        if fee.get("standard") is not None:
            return number(fee.get("standard")), "standard"
        return None, "unknown_subscription_condition"
    if fee is not None:
        return number(fee), "standard"
    return number(card.get("foreign_transaction_fee_percent")), "standard"


def active_promotions(card, as_of):
    active = []
    if as_of is None:
        return active
    for promo in card.get("promotions", []) or []:
        if not isinstance(promo, dict):
            continue
        start, end = iso_date(promo.get("start")), iso_date(promo.get("end"))
        if start is not None and end is not None and start <= as_of <= end:
            active.append(promo)
    return active


def reward_rate(card, priorities):
    rates = card.get("reward_rates", {}) or {}
    if not isinstance(rates, dict):
        return None, None
    candidates = []
    for category in priorities:
        value = number(rates.get(category))
        if value is not None:
            candidates.append((value, category))
    for fallback in ("all", "base"):
        value = number(rates.get(fallback))
        if value is not None:
            candidates.append((value, fallback))
    return max(candidates, default=(None, None), key=lambda item: item[0] if item[0] is not None else -1)


def requirement_check(condition, label, failures, unknowns):
    if condition is True:
        return
    if condition is False:
        failures.append(label)
    else:
        unknowns.append(label)


def eligibility_check(condition, label, failures, unknowns):
    if condition is True:
        return
    if condition is False:
        failures.append(label)
    else:
        unknowns.append(label)


def evaluate(card, customer, requirements, as_of):
    hard_failures, hard_unknowns = [], []
    eligibility_failures, eligibility_unknowns = [], []

    required_limit = number(requirements.get("minimum_credit_limit"))
    if required_limit is not None:
        maximum = limit_max(card)
        requirement_check(None if maximum is None else maximum >= required_limit,
                          "documented maximum credit limit does not reach the requested minimum" if maximum is not None else "maximum credit limit is not documented",
                          hard_failures, hard_unknowns)

    requested_fee = number(requirements.get("foreign_transaction_fee_percent"))
    if requested_fee is not None:
        fee, fee_basis = foreign_fee(card, customer.get("premium_subscription"))
        if fee_basis == "unknown_subscription_condition" and customer.get("premium_subscription") is None:
            condition = None
            label = "foreign transaction fee depends on an unknown subscription state"
        else:
            condition = None if fee is None else fee <= requested_fee
            label = "foreign transaction fee exceeds requested maximum" if fee is not None else "foreign transaction fee is not documented"
        requirement_check(condition, label, hard_failures, hard_unknowns)

    protection = card.get("purchase_protection")
    if requirements.get("purchase_protection") is True:
        exists = isinstance(protection, dict) and number(protection.get("days")) is not None
        requirement_check(exists if protection is not None else None,
                          "purchase protection is not documented", hard_failures, hard_unknowns)
    minimum_days = number(requirements.get("minimum_protection_days"))
    if minimum_days is not None:
        days = number(protection.get("days")) if isinstance(protection, dict) else None
        requirement_check(None if days is None else days >= minimum_days,
                          "purchase-protection duration is below the requested minimum" if days is not None else "purchase-protection duration is not documented",
                          hard_failures, hard_unknowns)

    if requirements.get("virtual_cards") is True:
        value = card.get("virtual_cards")
        requirement_check(value if isinstance(value, bool) else None,
                          "virtual cards are unavailable or not documented", hard_failures, hard_unknowns)

    eligibility = card.get("eligibility", {}) or {}
    if eligibility.get("premium_subscription_required") is True:
        subscription = customer.get("premium_subscription")
        eligibility_check(subscription if isinstance(subscription, bool) else None,
                          "required premium subscription is absent or unknown", eligibility_failures, eligibility_unknowns)
    if eligibility.get("invitation_only") is True:
        invitation = customer.get("has_invitation")
        eligibility_check(invitation if isinstance(invitation, bool) else None,
                          "card is invitation-only and no invitation is confirmed", eligibility_failures, eligibility_unknowns)
    minimum_score = number(eligibility.get("minimum_credit_score"))
    if minimum_score is not None:
        score = number(customer.get("credit_score"))
        eligibility_check(None if score is None else score >= minimum_score,
                          "minimum credit score is not met" if score is not None else "credit score is needed to assess the documented minimum",
                          eligibility_failures, eligibility_unknowns)

    rate, rate_category = reward_rate(card, customer.get("spend_priority", []) or [])
    match_status = "does_not_match" if hard_failures else ("needs_confirmation" if hard_unknowns else "matches")
    eligibility_status = "ineligible" if eligibility_failures else ("conditional" if eligibility_unknowns else "eligible")
    status_value = {"eligible": 2, "conditional": 1, "ineligible": 0}[eligibility_status]
    match_value = {"matches": 2, "needs_confirmation": 1, "does_not_match": 0}[match_status]
    utility = status_value * 10000 + match_value * 1000 + (rate or 0)

    return {
        "name": card.get("name", "Unnamed card"),
        "match_status": match_status,
        "eligibility_status": eligibility_status,
        "hard_requirement_failures": hard_failures,
        "hard_requirement_unknowns": hard_unknowns,
        "eligibility_failures": eligibility_failures,
        "eligibility_unknowns": eligibility_unknowns,
        "documented_limit_range": card.get("limit_range"),
        "documented_annual_fee": card.get("annual_fee"),
        "documented_purchase_protection": protection,
        "priority_reward_rate": rate,
        "priority_reward_category": rate_category,
        "active_promotions": active_promotions(card, as_of),
        "source_notes": card.get("source_notes", []),
        "ordering_utility": utility
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        cards = payload.get("cards")
        if not isinstance(cards, list) or not cards:
            raise ValueError("cards must be a non-empty array")
        customer = payload.get("customer", {})
        requirements = payload.get("requirements", {})
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be JSON objects")
        as_of = iso_date(payload.get("as_of"))
        results = [evaluate(card, customer, requirements, as_of) for card in cards if isinstance(card, dict)]
        if not results:
            raise ValueError("cards must contain at least one JSON object")
        results.sort(key=lambda item: (-item["ordering_utility"], item["name"]))
        best = results[0]
        print(json.dumps({
            "as_of_used": as_of.isoformat() if as_of else None,
            "best_available": best["name"],
            "best_available_is_conditional": best["eligibility_status"] != "eligible" or best["match_status"] != "matches",
            "results": results
        }, indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
