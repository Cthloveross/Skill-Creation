#!/usr/bin/env python3
"""Rank extracted credit-card terms against explicit customer preferences.

Input: JSON object described in SKILL.md on stdin.
Output: JSON object with recommendations, exclusions, and validation_errors.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value, field, errors, required=True):
    if value is None:
        if required:
            errors.append(f"{field} is required")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if result < 0:
        errors.append(f"{field} cannot be negative")
        return None
    return result


def display_decimal(value):
    return format(value.normalize(), "f") if value is not None else None


def subscription_state(required_subscription, statuses):
    if not required_subscription:
        return "not_required"
    state = statuses.get(str(required_subscription), "unknown")
    return state if state in {"active", "inactive", "unknown"} else "unknown"


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"recommendations": [], "excluded": [],
                          "validation_errors": [f"invalid JSON: {exc.msg}"]}))
        return

    errors = []
    if not isinstance(payload, dict):
        print(json.dumps({"recommendations": [], "excluded": [],
                          "validation_errors": ["top-level input must be an object"]}))
        return

    preferences = payload.get("preferences")
    cards = payload.get("cards")
    if not isinstance(preferences, dict):
        errors.append("preferences must be an object")
        preferences = {}
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    simple = preferences.get("simple_flat_cashback")
    if not isinstance(simple, bool):
        errors.append("preferences.simple_flat_cashback must be boolean")
        simple = False
    max_fee = decimal_value(preferences.get("max_annual_fee"),
                            "preferences.max_annual_fee", errors)
    score_raw = preferences.get("credit_score")
    score = None if score_raw is None else decimal_value(score_raw,
                                                           "preferences.credit_score", errors)
    statuses = preferences.get("subscription_status", {})
    if not isinstance(statuses, dict):
        errors.append("preferences.subscription_status must be an object when supplied")
        statuses = {}

    recommendations = []
    excluded = []
    valid_scopes = {"flat_all_eligible", "category_or_mixed", "unknown"}

    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        rate = decimal_value(card.get("cash_back_rate"), f"{prefix}.cash_back_rate", errors)
        fee = decimal_value(card.get("annual_fee"), f"{prefix}.annual_fee", errors)
        scope = card.get("cash_back_scope")
        if scope not in valid_scopes:
            errors.append(f"{prefix}.cash_back_scope must be flat_all_eligible, category_or_mixed, or unknown")
            scope = "unknown"

        min_score_raw = card.get("min_credit_score")
        min_score = None if min_score_raw is None else decimal_value(
            min_score_raw, f"{prefix}.min_credit_score", errors)
        required_subscription = card.get("required_subscription")
        if required_subscription is not None and not isinstance(required_subscription, str):
            errors.append(f"{prefix}.required_subscription must be a string or null")
            required_subscription = None

        reasons = []
        conditions = []
        if rate is None or fee is None:
            reasons.append("cash-back rate or annual fee is unverified")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual card fee exceeds stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("rewards are category-based or mixed, not the requested flat rate")
        if simple and scope == "unknown":
            conditions.append("confirm that the stated rate applies to all eligible purchases")

        sub_state = subscription_state(required_subscription, statuses)
        if sub_state == "inactive":
            reasons.append("required subscription is known inactive")
        elif sub_state == "unknown":
            conditions.append(f"confirm active required subscription: {required_subscription}")

        if min_score is not None:
            if score is None:
                conditions.append(f"meet the minimum credit score of {display_decimal(min_score)}")
            elif score < min_score:
                reasons.append(f"credit score is below the minimum of {display_decimal(min_score)}")

        record = {
            "name": name,
            "cash_back_rate_percent": display_decimal(rate),
            "cash_back_scope": scope,
            "annual_fee": display_decimal(fee),
            "required_subscription": required_subscription,
            "subscription_status": sub_state,
            "minimum_credit_score": display_decimal(min_score),
            "source_notes": card.get("source_notes", []),
        }
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            record["eligibility"] = "eligible" if not conditions else "conditional"
            recommendations.append(record)

    # Higher cash back is better. At the same rate, a confirmed match precedes a conditional one.
    recommendations.sort(key=lambda item: (
        -Decimal(item["cash_back_rate_percent"] or "0"),
        0 if item["eligibility"] == "eligible" else 1,
        item["name"].casefold(),
    ))
    excluded.sort(key=lambda item: item["name"].casefold())

    print(json.dumps({
        "recommendations": recommendations,
        "excluded": excluded,
        "validation_errors": errors,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
