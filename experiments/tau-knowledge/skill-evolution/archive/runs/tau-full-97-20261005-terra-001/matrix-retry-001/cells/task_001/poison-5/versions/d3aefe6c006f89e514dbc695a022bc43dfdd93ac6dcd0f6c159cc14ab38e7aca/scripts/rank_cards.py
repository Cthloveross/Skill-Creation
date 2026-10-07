#!/usr/bin/env python3
"""Rank already-extracted credit-card facts against explicit preferences.

Read one JSON object from stdin and emit:
{"recommendations": [...], "excluded": [...], "validation_errors": [...]}.
The script neither retrieves evidence nor makes an eligibility decision.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
STATES = {"active", "inactive", "unknown"}


def emit(recommendations, excluded, errors):
    print(json.dumps({"recommendations": recommendations, "excluded": excluded,
                      "validation_errors": errors}, ensure_ascii=False))


def numeric(value, label, errors, required=True):
    if value is None:
        if required:
            errors.append(f"{label} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not value.is_finite() or value < 0:
        errors.append(f"{label} must be a nonnegative finite number")
        return None
    return value


def display(value):
    if value is None:
        return None
    result = format(value.normalize(), "f")
    return "0" if result in {"", "-0"} else result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit([], [], [f"invalid JSON: {exc.msg}"])
        return
    if not isinstance(payload, dict):
        emit([], [], ["top-level input must be an object"])
        return

    errors = []
    preferences = payload.get("preferences")
    cards = payload.get("cards")
    if not isinstance(preferences, dict):
        preferences = {}
        errors.append("preferences must be an object")
    if not isinstance(cards, list):
        cards = []
        errors.append("cards must be an array")

    simple = preferences.get("simple_flat_cashback")
    if not isinstance(simple, bool):
        simple = False
        errors.append("preferences.simple_flat_cashback must be boolean")
    max_fee = numeric(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    raw_score = preferences.get("credit_score")
    score = None if raw_score is None else numeric(raw_score, "preferences.credit_score", errors)

    supplied_states = preferences.get("subscription_status", {})
    if not isinstance(supplied_states, dict):
        supplied_states = {}
        errors.append("preferences.subscription_status must be an object")
    states = {}
    for membership, state in supplied_states.items():
        if not isinstance(membership, str) or not membership.strip() or state not in STATES:
            errors.append("subscription_status has an invalid membership name or state")
        else:
            states[membership.strip()] = state

    recommendations, excluded = [], []
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        rate = numeric(card.get("cash_back_rate"), f"{prefix}.cash_back_rate", errors)
        fee = numeric(card.get("annual_fee"), f"{prefix}.annual_fee", errors)
        scope = card.get("cash_back_scope")
        if scope not in SCOPES:
            scope = "unknown"
            errors.append(f"{prefix}.cash_back_scope is invalid")
        subscription = card.get("required_subscription")
        if subscription is not None and (not isinstance(subscription, str) or not subscription.strip()):
            subscription = None
            errors.append(f"{prefix}.required_subscription must be a nonempty string or null")
        elif isinstance(subscription, str):
            subscription = subscription.strip()
        raw_minimum = card.get("min_credit_score")
        minimum = None if raw_minimum is None else numeric(raw_minimum, f"{prefix}.min_credit_score", errors)

        reasons, conditions = [], []
        if rate is None or fee is None:
            reasons.append("cash-back rate or annual card fee is unverified")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual card fee exceeds the stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("rewards are category-based or mixed, not the requested flat rate")
        if simple and scope == "unknown":
            conditions.append("confirm whether the rate applies to all eligible purchases")

        state = "not_required" if subscription is None else states.get(subscription, "unknown")
        if state == "inactive":
            reasons.append("required subscription is known inactive")
        elif state == "unknown":
            conditions.append(f"confirm active required subscription: {subscription}")
        if minimum is not None:
            if score is None:
                conditions.append(f"meet the minimum credit score of {display(minimum)}")
            elif score < minimum:
                reasons.append(f"credit score is below the minimum of {display(minimum)}")

        record = {
            "name": name.strip(), "cash_back_rate_percent": display(rate),
            "cash_back_scope": scope, "annual_fee": display(fee),
            "required_subscription": subscription, "subscription_status": state,
            "minimum_credit_score": display(minimum)
        }
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            record["eligibility"] = "conditional" if conditions else "eligible"
            recommendations.append(record)

    recommendations.sort(key=lambda item: (
        -Decimal(item["cash_back_rate_percent"] or "0"),
        0 if item["eligibility"] == "eligible" else 1,
        item["name"].casefold(),
    ))
    excluded.sort(key=lambda item: item["name"].casefold())
    emit(recommendations, excluded, errors)


if __name__ == "__main__":
    main()
