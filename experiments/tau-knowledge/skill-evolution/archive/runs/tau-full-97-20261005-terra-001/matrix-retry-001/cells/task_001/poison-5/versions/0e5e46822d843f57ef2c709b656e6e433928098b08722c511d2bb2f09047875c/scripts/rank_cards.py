#!/usr/bin/env python3
"""Rank documented card terms against explicit customer preferences.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not retrieve documents and performs no network, account, file, or tool access.

Input and output schemas are documented in SKILL.md.
"""

import json
import sys
from decimal import Decimal, InvalidOperation

VALID_SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
VALID_SUBSCRIPTION_STATES = {"active", "inactive", "unknown"}


def emit(recommendations, excluded, validation_errors):
    print(json.dumps({
        "recommendations": recommendations,
        "excluded": excluded,
        "validation_errors": validation_errors,
    }, ensure_ascii=False))


def decimal_value(value, field, errors, required=True):
    if value is None:
        if required:
            errors.append(f"{field} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{field} must be a nonnegative finite number")
        return None
    return number


def display_decimal(number):
    if number is None:
        return None
    rendered = format(number.normalize(), "f")
    return "0" if rendered in {"-0", ""} else rendered


def required_subscription_status(subscription, statuses):
    if not subscription:
        return "not_required"
    return statuses.get(subscription, "unknown")


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
        errors.append("preferences must be an object")
        preferences = {}
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    simple = preferences.get("simple_flat_cashback")
    if not isinstance(simple, bool):
        errors.append("preferences.simple_flat_cashback must be boolean")
        simple = False
    max_fee = decimal_value(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    score_raw = preferences.get("credit_score")
    score = None if score_raw is None else decimal_value(score_raw, "preferences.credit_score", errors)

    statuses = {}
    supplied_statuses = preferences.get("subscription_status", {})
    if not isinstance(supplied_statuses, dict):
        errors.append("preferences.subscription_status must be an object when supplied")
    else:
        for membership, status in supplied_statuses.items():
            if not isinstance(membership, str) or not membership.strip():
                errors.append("subscription-status membership names must be nonempty strings")
                continue
            if status not in VALID_SUBSCRIPTION_STATES:
                errors.append(f"subscription status for {membership} is invalid")
                continue
            statuses[membership.strip()] = status

    recommendations = []
    excluded = []
    for index, raw_card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(raw_card, dict):
            errors.append(f"{prefix} must be an object")
            continue

        name = raw_card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        name = name.strip()
        rate = decimal_value(raw_card.get("cash_back_rate"), f"{prefix}.cash_back_rate", errors)
        fee = decimal_value(raw_card.get("annual_fee"), f"{prefix}.annual_fee", errors)
        scope = raw_card.get("cash_back_scope")
        if scope not in VALID_SCOPES:
            errors.append(f"{prefix}.cash_back_scope is invalid")
            scope = "unknown"

        subscription = raw_card.get("required_subscription")
        if subscription is not None:
            if not isinstance(subscription, str):
                errors.append(f"{prefix}.required_subscription must be a string or null")
                subscription = None
            else:
                subscription = subscription.strip() or None
        raw_minimum = raw_card.get("min_credit_score")
        minimum = None if raw_minimum is None else decimal_value(
            raw_minimum, f"{prefix}.min_credit_score", errors
        )
        notes = raw_card.get("source_notes", [])
        if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
            errors.append(f"{prefix}.source_notes must be an array of strings when supplied")
            notes = []

        reasons = []
        conditions = []
        if rate is None or fee is None:
            reasons.append("cash-back rate or annual card fee is unverified")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual card fee exceeds the stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("rewards are category-based or mixed, not the requested flat rate")
        elif simple and scope == "unknown":
            conditions.append("confirm that the rate applies to all eligible purchases")

        subscription_state = required_subscription_status(subscription, statuses)
        if subscription_state == "inactive":
            reasons.append("required subscription is known inactive")
        elif subscription_state == "unknown":
            conditions.append(f"confirm active required subscription: {subscription}")

        if minimum is not None:
            minimum_text = display_decimal(minimum)
            if score is None:
                conditions.append(f"meet the minimum credit score of {minimum_text}")
            elif score < minimum:
                reasons.append(f"credit score is below the minimum of {minimum_text}")

        record = {
            "name": name,
            "cash_back_rate_percent": display_decimal(rate),
            "cash_back_scope": scope,
            "annual_fee": display_decimal(fee),
            "required_subscription": subscription,
            "subscription_status": subscription_state,
            "minimum_credit_score": display_decimal(minimum),
            "source_notes": notes,
        }
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            record["eligibility"] = "eligible" if not conditions else "conditional"
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
