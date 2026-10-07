#!/usr/bin/env python3
"""Deterministically screen normalized credit-card facts supplied as JSON."""

import json
import math
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def as_bool(value):
    return value if isinstance(value, bool) else None


def display_value(value):
    if value is None:
        return None
    return value


def normalized_subscriptions(value):
    if not isinstance(value, list):
        return None
    result = set()
    for item in value:
        if isinstance(item, str) and item.strip():
            result.add(item.strip().casefold())
    return result


def requirement_list(value):
    if value is None or value == "unknown":
        return None
    if isinstance(value, str):
        if value.strip().casefold() == "none":
            return []
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value):
        return value
    return None


def numeric_preference(value, threshold, label, comparison):
    if not is_number(threshold):
        return None, None
    if not is_number(value):
        return "unknown", "%s is not documented" % label
    passed = value <= threshold if comparison == "max" else value >= threshold
    if passed:
        return "pass", None
    symbol = "<=" if comparison == "max" else ">="
    return "fail", "%s (%s) does not satisfy %s %s" % (label, value, symbol, threshold)


def assess_card(card, customer, criteria):
    name = card.get("name")
    preferences = {}
    preference_failures = []
    preference_unknowns = []

    fee_status, fee_note = numeric_preference(
        card.get("foreign_transaction_fee_pct"),
        criteria.get("max_foreign_transaction_fee_pct"),
        "foreign transaction fee percentage", "max"
    )
    if fee_status is not None:
        preferences["foreign_transaction_fee"] = fee_status
        if fee_status == "fail":
            preference_failures.append(fee_note)
        elif fee_status == "unknown":
            preference_unknowns.append(fee_note)

    payment_status, payment_note = numeric_preference(
        card.get("minimum_payment_pct"),
        criteria.get("max_minimum_payment_pct"),
        "minimum payment percentage", "max"
    )
    if payment_status is not None:
        preferences["minimum_payment"] = payment_status
        if payment_status == "fail":
            preference_failures.append(payment_note)
        elif payment_status == "unknown":
            preference_unknowns.append(payment_note)

    required_virtual = criteria.get("requires_virtual_card_management")
    if isinstance(required_virtual, bool) and required_virtual:
        virtual = as_bool(card.get("virtual_card_management"))
        if virtual is True:
            preferences["virtual_card_management"] = "pass"
        elif virtual is False:
            preferences["virtual_card_management"] = "fail"
            preference_failures.append("virtual card management is unavailable")
        else:
            preferences["virtual_card_management"] = "unknown"
            preference_unknowns.append("virtual card management availability is not documented")

    blockers = []
    unknowns = []
    stated_score = customer.get("credit_score")
    required_score = card.get("minimum_credit_score")
    if is_number(required_score):
        if is_number(stated_score):
            if stated_score < required_score:
                blockers.append("stated credit score (%s) is below the disclosed minimum (%s)" % (stated_score, required_score))
        else:
            unknowns.append("customer credit score was not supplied")
    else:
        unknowns.append("minimum credit-score requirement is not documented")

    required_subscriptions = requirement_list(card.get("subscription_requirement"))
    customer_subscriptions = normalized_subscriptions(customer.get("subscriptions"))
    if required_subscriptions is None:
        unknowns.append("subscription requirement is not documented")
    elif required_subscriptions:
        if customer_subscriptions is None:
            unknowns.append("customer subscription status was not supplied")
        else:
            missing = [item for item in required_subscriptions if item.casefold() not in customer_subscriptions]
            if missing:
                blockers.append("required subscription missing: %s" % ", ".join(missing))

    invitation_only = as_bool(card.get("invitation_only"))
    if invitation_only is True:
        blockers.append("card is invitation-only")
    elif invitation_only is None:
        unknowns.append("invitation-only status is not documented")

    income_minimum = card.get("minimum_annual_income")
    stated_income = customer.get("annual_income")
    if is_number(income_minimum):
        if is_number(stated_income):
            if stated_income < income_minimum:
                blockers.append("stated annual income (%s) is below the disclosed minimum (%s)" % (stated_income, income_minimum))
        else:
            unknowns.append("customer annual income was not supplied")

    active_preferences = [status for status in preferences.values()]
    matches_all = bool(active_preferences) and all(status == "pass" for status in active_preferences)
    if matches_all and not blockers:
        tier = "qualified_match" if not unknowns else "criteria_match_with_unknown_eligibility"
    elif preference_failures:
        tier = "does_not_meet_preferences"
    elif blockers:
        tier = "known_eligibility_blocker"
    else:
        tier = "insufficient_documentation"

    return {
        "name": name,
        "tier": tier,
        "matches_all_preferences": matches_all,
        "preferences": preferences,
        "preference_failures": preference_failures,
        "preference_unknowns": preference_unknowns,
        "eligibility_blockers": blockers,
        "eligibility_unknowns": unknowns,
        "documented_terms": {
            "foreign_transaction_fee_pct": display_value(card.get("foreign_transaction_fee_pct")),
            "minimum_payment_pct": display_value(card.get("minimum_payment_pct")),
            "virtual_card_management": display_value(card.get("virtual_card_management")),
            "minimum_credit_score": display_value(card.get("minimum_credit_score")),
            "subscription_requirement": display_value(card.get("subscription_requirement")),
            "invitation_only": display_value(card.get("invitation_only"))
        },
        "application_notes": card.get("application_notes"),
        "source_notes": card.get("source_notes")
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["top-level JSON value must be an object"]}))
        return

    errors = []
    customer = payload.get("customer")
    criteria = payload.get("criteria")
    cards = payload.get("cards")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
    if not isinstance(criteria, dict):
        errors.append("criteria must be an object")
    if not isinstance(cards, list):
        errors.append("cards must be a list")
    if isinstance(cards, list):
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append("cards[%d] must be an object" % index)
            elif not isinstance(card.get("name"), str) or not card["name"].strip():
                errors.append("cards[%d].name must be a nonempty string" % index)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return

    assessments = [assess_card(card, customer, criteria) for card in cards]
    tier_rank = {
        "qualified_match": 0,
        "criteria_match_with_unknown_eligibility": 1,
        "known_eligibility_blocker": 2,
        "does_not_meet_preferences": 3,
        "insufficient_documentation": 4,
    }
    assessments.sort(key=lambda item: (
        tier_rank[item["tier"]],
        len(item["preference_failures"]),
        len(item["eligibility_blockers"]),
        item["name"].casefold(),
    ))
    recommendations = [item for item in assessments if item["tier"] == "qualified_match"]
    near_matches = [item for item in assessments if item["tier"] != "qualified_match"]
    result = {
        "ok": True,
        "summary": {
            "cards_evaluated": len(assessments),
            "qualified_matches": len(recommendations),
            "statement": (
                "One or more cards meet all confirmed preferences with no known disclosed eligibility blocker."
                if recommendations else
                "No card is a confirmed qualified match from the supplied documentation."
            )
        },
        "recommendations": recommendations,
        "near_matches": near_matches,
        "all_assessments": assessments,
        "disclaimer": "Results compare supplied documentation and stated customer information only; they are not an approval or underwriting decision."
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
