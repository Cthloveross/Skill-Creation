#!/usr/bin/env python3
"""Screen normalized, source-backed credit-card facts from JSON stdin."""
import json
import math
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def customer_subscriptions(value):
    if not isinstance(value, list):
        return None
    return {item.strip().casefold() for item in value if isinstance(item, str) and item.strip()}


def required_subscriptions(value):
    if value is None or value == "unknown":
        return None
    if isinstance(value, str):
        return [] if value.strip().casefold() == "none" else [value]
    if isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value):
        return value
    return None


def cap_result(value, cap, label):
    if cap is None:
        return None, None
    if not is_number(cap):
        return "unknown", "requested %s cap is invalid" % label
    if not is_number(value):
        return "unknown", "%s is not documented" % label
    if value <= cap:
        return "pass", None
    return "fail", "%s (%.3g%%) exceeds requested cap (%.3g%%)" % (label, value, cap)


def assess(card, customer, criteria):
    results = {}
    feature_failures, feature_unknowns = [], []
    checks = (
        ("foreign_transaction_fee", "foreign_transaction_fee_pct", "max_foreign_transaction_fee_pct", "foreign transaction fee"),
        ("minimum_payment", "minimum_payment_pct", "max_minimum_payment_pct", "minimum payment"),
    )
    for result_key, card_key, criteria_key, label in checks:
        status, note = cap_result(card.get(card_key), criteria.get(criteria_key), label)
        if status is not None:
            results[result_key] = status
            if status == "fail":
                feature_failures.append(note)
            elif status == "unknown":
                feature_unknowns.append(note)

    if criteria.get("requires_virtual_card_management") is True:
        virtual = card.get("virtual_card_management")
        if virtual is True:
            results["virtual_card_management"] = "pass"
        elif virtual is False:
            results["virtual_card_management"] = "fail"
            feature_failures.append("virtual card management is unavailable")
        else:
            results["virtual_card_management"] = "unknown"
            feature_unknowns.append("virtual card management availability is not documented")

    blockers, eligibility_unknowns = [], []
    minimum_score = card.get("minimum_credit_score")
    stated_score = customer.get("credit_score")
    if is_number(minimum_score):
        if is_number(stated_score):
            if stated_score < minimum_score:
                blockers.append("stated credit score (%s) is below disclosed minimum (%s)" % (stated_score, minimum_score))
        else:
            eligibility_unknowns.append("customer credit score was not supplied")
    else:
        eligibility_unknowns.append("minimum credit-score requirement is not documented")

    required = required_subscriptions(card.get("subscription_requirement"))
    held = customer_subscriptions(customer.get("subscriptions"))
    if required is None:
        eligibility_unknowns.append("subscription requirement is not documented")
    elif required:
        if held is None:
            eligibility_unknowns.append("customer subscription status was not supplied")
        else:
            missing = [name for name in required if name.casefold() not in held]
            if missing:
                blockers.append("required subscription missing: " + ", ".join(missing))

    invitation = card.get("invitation_only")
    if invitation is True:
        blockers.append("card is invitation-only")
    elif invitation not in (False, None):
        eligibility_unknowns.append("invitation-only status is malformed")

    minimum_income = card.get("minimum_annual_income")
    income = customer.get("annual_income")
    if is_number(minimum_income):
        if is_number(income) and income < minimum_income:
            blockers.append("stated annual income (%s) is below disclosed minimum (%s)" % (income, minimum_income))
        elif not is_number(income):
            eligibility_unknowns.append("customer annual income was not supplied")

    active_results = list(results.values())
    all_features_pass = bool(active_results) and all(status == "pass" for status in active_results)
    if all_features_pass and not blockers:
        tier = "documented_fit"
    elif feature_failures:
        tier = "does_not_meet_preferences"
    elif blockers:
        tier = "known_eligibility_blocker"
    else:
        tier = "insufficient_documentation"

    terms = {key: card.get(key) for key in (
        "foreign_transaction_fee_pct", "minimum_payment_pct", "virtual_card_management",
        "minimum_credit_score", "subscription_requirement", "invitation_only",
        "minimum_annual_income")}
    return {
        "name": card["name"],
        "tier": tier,
        "matches_all_preferences": all_features_pass,
        "preference_results": results,
        "preference_failures": feature_failures,
        "preference_unknowns": feature_unknowns,
        "eligibility_blockers": blockers,
        "eligibility_unknowns": eligibility_unknowns,
        "documented_terms": terms,
        "source_notes": card.get("source_notes", []),
    }


def validate(payload):
    errors = []
    if not isinstance(payload, dict):
        return ["top-level JSON value must be an object"]
    if not isinstance(payload.get("customer"), dict):
        errors.append("customer must be an object")
    if not isinstance(payload.get("criteria"), dict):
        errors.append("criteria must be an object")
    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be a list")
    elif any(not isinstance(card, dict) or not isinstance(card.get("name"), str) or not card["name"].strip() for card in cards):
        errors.append("each card must be an object with a nonempty name")
    return errors


def screen(payload):
    errors = validate(payload)
    if errors:
        return {"ok": False, "errors": errors}
    assessments = [assess(card, payload["customer"], payload["criteria"]) for card in payload["cards"]]
    order = {"documented_fit": 0, "known_eligibility_blocker": 1, "does_not_meet_preferences": 2, "insufficient_documentation": 3}
    assessments.sort(key=lambda item: (order[item["tier"]], len(item["eligibility_blockers"]), item["name"].casefold()))
    fits = [item for item in assessments if item["tier"] == "documented_fit"]
    return {
        "ok": True,
        "summary": {"cards_evaluated": len(assessments), "documented_fits": len(fits)},
        "recommendations": fits,
        "alternatives": [item for item in assessments if item["tier"] != "documented_fit"],
        "assessments": assessments,
        "disclaimer": "This is a comparison of supplied terms and stated facts, not an approval or underwriting decision.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return
    print(json.dumps(screen(payload), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
