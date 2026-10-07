#!/usr/bin/env python3
"""Rank supplied credit-card records against explicit customer requirements.

Reads one JSON object from stdin and writes one JSON object to stdout.  It uses
only Python's standard library and does not read accounts or perform actions.
"""
import json
import sys
from numbers import Real


def number(value):
    return isinstance(value, Real) and not isinstance(value, bool)


def as_dict(value):
    return value if isinstance(value, dict) else {}


def as_list(value):
    return value if isinstance(value, list) else []


def reward_for(card, category):
    rewards = as_dict(card.get("rewards"))
    category_rates = as_dict(rewards.get("categories"))
    rate = category_rates.get(category)
    if number(rate):
        return rate, "category"
    rate = rewards.get("all")
    if number(rate):
        return rate, "all_purchases"
    return None, "unknown"


def evaluate(card, requirements):
    matched, failures, conditions = [], [], []
    name = card.get("name") if isinstance(card.get("name"), str) else "Unnamed card"
    audience = card.get("audience", "both")
    applicant_type = requirements.get("applicant_type", "unknown")
    if applicant_type not in ("personal", "business", "unknown"):
        failures.append("invalid applicant_type")
    elif audience not in ("personal", "business", "both"):
        conditions.append("product audience is not documented")
    elif applicant_type == "unknown" and audience in ("personal", "business"):
        conditions.append("confirm applicant type; this is a %s product" % audience)
    elif applicant_type != "unknown" and audience not in ("both", applicant_type):
        failures.append("product audience is %s, not %s" % (audience, applicant_type))

    desired_fee = requirements.get("foreign_transaction_fee_pct")
    actual_fee = card.get("foreign_transaction_fee_pct")
    if desired_fee is not None:
        if not number(desired_fee):
            failures.append("requested foreign transaction fee is not numeric")
        elif not number(actual_fee):
            failures.append("foreign transaction fee is undocumented")
        elif actual_fee > desired_fee:
            failures.append("foreign transaction fee exceeds requested maximum")
        else:
            matched.append("foreign transaction fee")
    for item in as_list(card.get("foreign_fee_conditions")):
        if isinstance(item, str) and item:
            conditions.append(item)

    if requirements.get("requires_purchase_protection") is True:
        protection = as_dict(card.get("purchase_protection"))
        if not protection:
            failures.append("purchase protection is undocumented")
        else:
            matched.append("purchase protection")
            if not number(protection.get("days")):
                conditions.append("purchase-protection window is not documented")
            if not number(protection.get("max_claim")):
                conditions.append("purchase-protection claim cap is not documented")

    required_limit = requirements.get("minimum_possible_limit")
    maximum = as_dict(card.get("limits")).get("maximum")
    if required_limit is not None:
        if not number(required_limit):
            failures.append("requested possible limit is not numeric")
        elif not number(maximum):
            failures.append("maximum available limit is undocumented")
        elif maximum < required_limit:
            failures.append("documented maximum limit is below requested amount")
        else:
            matched.append("possible credit limit")
            conditions.append("actual credit limit is determined by underwriting")

    category = requirements.get("spending_category")
    rate, rate_basis = reward_for(card, category) if isinstance(category, str) and category else (None, "not_requested")
    if isinstance(category, str) and category and rate is None:
        conditions.append("%s reward rate is not documented" % category)

    for item in as_list(card.get("conditions")):
        if isinstance(item, str) and item:
            conditions.append(item)

    # Preserve order while avoiding repetitive disclosure text.
    conditions = list(dict.fromkeys(conditions))
    return {
        "name": name,
        "status": "eligible" if not failures and not conditions else ("rejected" if failures else "conditional"),
        "matched_requirements": matched,
        "failures": failures,
        "conditions_to_disclose": conditions,
        "reward_rate_pct": rate,
        "reward_rate_basis": rate_basis,
        "documented_maximum_limit": maximum if number(maximum) else None,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ranked": [], "rejected": [], "input_errors": ["invalid JSON: %s" % exc]}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"ranked": [], "rejected": [], "input_errors": ["top-level JSON must be an object"]}))
        return
    requirements = payload.get("requirements", {})
    cards = payload.get("cards", [])
    errors = []
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    ranked, rejected = [], []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            errors.append("cards[%d] must be an object" % index)
            continue
        result = evaluate(card, requirements)
        (rejected if result["failures"] else ranked).append(result)

    # Eligible precedes conditional; then favor the requested-category reward,
    # then documented maximum limit. Unknown values sort last.
    def ranking_key(item):
        return (
            0 if item["status"] == "eligible" else 1,
            -(item["reward_rate_pct"] if number(item["reward_rate_pct"]) else -1),
            -(item["documented_maximum_limit"] if number(item["documented_maximum_limit"]) else -1),
            item["name"].lower(),
        )
    ranked.sort(key=ranking_key)
    print(json.dumps({"ranked": ranked, "rejected": rejected, "input_errors": errors}, sort_keys=True))


if __name__ == "__main__":
    main()
