#!/usr/bin/env python3
"""Screen normalized, source-backed credit-card facts supplied as JSON."""
import json
import math
import sys


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def subscriptions(value):
    if not isinstance(value, list):
        return None
    return {x.strip().casefold() for x in value if isinstance(x, str) and x.strip()}


def requirements(value):
    if value is None or value == "unknown":
        return None
    if isinstance(value, str):
        return [] if value.strip().casefold() == "none" else [value]
    if isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value):
        return value
    return None


def max_check(value, maximum, label):
    if maximum is None:
        return None, None
    if not number(maximum):
        return "unknown", "requested %s cap is invalid" % label
    if not number(value):
        return "unknown", "%s is not documented" % label
    if value <= maximum:
        return "pass", None
    return "fail", "%s (%s%%) exceeds requested cap (%s%%)" % (label, value, maximum)


def assess(card, customer, criteria):
    results, preference_failures, preference_unknowns = {}, [], []
    for key, card_key, criterion_key, label in (
        ("foreign_transaction_fee", "foreign_transaction_fee_pct", "max_foreign_transaction_fee_pct", "foreign transaction fee"),
        ("minimum_payment", "minimum_payment_pct", "max_minimum_payment_pct", "minimum payment"),
    ):
        status, note = max_check(card.get(card_key), criteria.get(criterion_key), label)
        if status:
            results[key] = status
            if status == "fail":
                preference_failures.append(note)
            elif status == "unknown":
                preference_unknowns.append(note)

    if criteria.get("requires_virtual_card_management") is True:
        value = card.get("virtual_card_management")
        if value is True:
            results["virtual_card_management"] = "pass"
        elif value is False:
            results["virtual_card_management"] = "fail"
            preference_failures.append("virtual card management is unavailable")
        else:
            results["virtual_card_management"] = "unknown"
            preference_unknowns.append("virtual card management availability is not documented")

    blockers, unknowns = [], []
    required_score, stated_score = card.get("minimum_credit_score"), customer.get("credit_score")
    if number(required_score):
        if number(stated_score):
            if stated_score < required_score:
                blockers.append("stated credit score (%s) is below disclosed minimum (%s)" % (stated_score, required_score))
        else:
            unknowns.append("customer credit score was not supplied")
    else:
        unknowns.append("minimum credit-score requirement is not documented")

    required_subs, stated_subs = requirements(card.get("subscription_requirement")), subscriptions(customer.get("subscriptions"))
    if required_subs is None:
        unknowns.append("subscription requirement is not documented")
    elif required_subs:
        if stated_subs is None:
            unknowns.append("customer subscription status was not supplied")
        else:
            missing = [x for x in required_subs if x.casefold() not in stated_subs]
            if missing:
                blockers.append("required subscription missing: " + ", ".join(missing))

    invitation = card.get("invitation_only")
    if invitation is True:
        blockers.append("card is invitation-only")
    elif invitation not in (False, None):
        unknowns.append("invitation-only status is malformed")

    income_min, income = card.get("minimum_annual_income"), customer.get("annual_income")
    if number(income_min):
        if number(income) and income < income_min:
            blockers.append("stated annual income (%s) is below disclosed minimum (%s)" % (income, income_min))
        elif not number(income):
            unknowns.append("customer annual income was not supplied")

    active = list(results.values())
    all_preferences_pass = bool(active) and all(x == "pass" for x in active)
    if all_preferences_pass and not blockers:
        tier = "documented_fit"
    elif preference_failures:
        tier = "does_not_meet_preferences"
    elif blockers:
        tier = "known_eligibility_blocker"
    else:
        tier = "insufficient_documentation"

    return {
        "name": card["name"], "tier": tier,
        "matches_all_preferences": all_preferences_pass,
        "preference_results": results,
        "preference_failures": preference_failures,
        "preference_unknowns": preference_unknowns,
        "eligibility_blockers": blockers,
        "eligibility_unknowns": unknowns,
        "documented_terms": {
            "foreign_transaction_fee_pct": card.get("foreign_transaction_fee_pct"),
            "minimum_payment_pct": card.get("minimum_payment_pct"),
            "virtual_card_management": card.get("virtual_card_management"),
            "minimum_credit_score": card.get("minimum_credit_score"),
            "subscription_requirement": card.get("subscription_requirement"),
            "invitation_only": card.get("invitation_only"),
            "minimum_annual_income": card.get("minimum_annual_income")
        },
        "source_notes": card.get("source_notes", [])
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
    customer, criteria, cards = payload.get("customer"), payload.get("criteria"), payload.get("cards")
    errors = []
    if not isinstance(customer, dict): errors.append("customer must be an object")
    if not isinstance(criteria, dict): errors.append("criteria must be an object")
    if not isinstance(cards, list): errors.append("cards must be a list")
    if isinstance(cards, list):
        for i, card in enumerate(cards):
            if not isinstance(card, dict) or not isinstance(card.get("name"), str) or not card["name"].strip():
                errors.append("cards[%d] must be an object with a nonempty name" % i)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return

    assessments = [assess(c, customer, criteria) for c in cards]
    order = {"documented_fit": 0, "known_eligibility_blocker": 1, "does_not_meet_preferences": 2, "insufficient_documentation": 3}
    assessments.sort(key=lambda x: (order[x["tier"]], len(x["preference_failures"]), len(x["eligibility_blockers"]), x["name"].casefold()))
    recommendations = [x for x in assessments if x["tier"] == "documented_fit"]
    print(json.dumps({
        "ok": True,
        "summary": {"cards_evaluated": len(assessments), "documented_fits": len(recommendations)},
        "recommendations": recommendations,
        "alternatives": [x for x in assessments if x["tier"] != "documented_fit"],
        "assessments": assessments,
        "disclaimer": "This compares supplied product terms with stated customer facts. It is not an approval or underwriting decision."
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
