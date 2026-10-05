#!/usr/bin/env python3
"""Rank documented credit-card terms against explicit customer preferences.

Reads one JSON object from stdin and writes one JSON object to stdout.
No account, network, file, or tool access is performed.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


VALID_SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
VALID_SUBSCRIPTION_STATES = {"active", "inactive", "unknown"}


def output(recommendations, excluded, validation_errors):
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
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{field} must be a nonnegative finite number")
        return None
    return result


def display_decimal(value):
    if value is None:
        return None
    rendered = format(value.normalize(), "f")
    return "0" if rendered == "-0" else rendered


def subscription_state(required_subscription, statuses):
    if not required_subscription:
        return "not_required"
    state = statuses.get(required_subscription, "unknown")
    return state if state in VALID_SUBSCRIPTION_STATES else "unknown"


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output([], [], [f"invalid JSON: {exc.msg}"])
        return

    if not isinstance(payload, dict):
        output([], [], ["top-level input must be an object"])
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

    max_fee = decimal_value(
        preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors
    )
    raw_score = preferences.get("credit_score")
    score = None if raw_score is None else decimal_value(
        raw_score, "preferences.credit_score", errors
    )

    statuses = preferences.get("subscription_status", {})
    if not isinstance(statuses, dict):
        errors.append("preferences.subscription_status must be an object when supplied")
        statuses = {}
    else:
        normalized_statuses = {}
        for membership, state in statuses.items():
            if not isinstance(membership, str) or not membership.strip():
                errors.append("subscription-status membership names must be nonempty strings")
                continue
            if state not in VALID_SUBSCRIPTION_STATES:
                errors.append(
                    f"subscription status for {membership} must be active, inactive, or unknown"
                )
                normalized_statuses[membership] = "unknown"
            else:
                normalized_statuses[membership] = state
        statuses = normalized_statuses

    recommendations = []
    excluded = []

    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{prefix} must be an object")
            continue

        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        name = name.strip()

        rate = decimal_value(card.get("cash_back_rate"), f"{prefix}.cash_back_rate", errors)
        fee = decimal_value(card.get("annual_fee"), f"{prefix}.annual_fee", errors)
        scope = card.get("cash_back_scope")
        if scope not in VALID_SCOPES:
            errors.append(
                f"{prefix}.cash_back_scope must be flat_all_eligible, category_or_mixed, or unknown"
            )
            scope = "unknown"

        required_subscription = card.get("required_subscription")
        if required_subscription is not None:
            if not isinstance(required_subscription, str):
                errors.append(f"{prefix}.required_subscription must be a string or null")
                required_subscription = None
            else:
                required_subscription = required_subscription.strip() or None

        raw_minimum = card.get("min_credit_score")
        minimum_score = None if raw_minimum is None else decimal_value(
            raw_minimum, f"{prefix}.min_credit_score", errors
        )

        source_notes = card.get("source_notes", [])
        if not isinstance(source_notes, list) or not all(isinstance(x, str) for x in source_notes):
            errors.append(f"{prefix}.source_notes must be an array of strings when supplied")
            source_notes = []

        reasons = []
        conditions = []
        if rate is None or fee is None:
            reasons.append("cash-back rate or annual card fee is unverified")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual card fee exceeds the stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("rewards are category-based or mixed, not the requested flat rate")
        elif simple and scope == "unknown":
            conditions.append("confirm that the stated rate applies to all eligible purchases")

        state = subscription_state(required_subscription, statuses)
        if state == "inactive":
            reasons.append("required subscription is known inactive")
        elif state == "unknown":
            conditions.append(f"confirm active required subscription: {required_subscription}")

        if minimum_score is not None:
            minimum_display = display_decimal(minimum_score)
            if score is None:
                conditions.append(f"meet the minimum credit score of {minimum_display}")
            elif score < minimum_score:
                reasons.append(f"credit score is below the minimum of {minimum_display}")

        record = {
            "name": name,
            "cash_back_rate_percent": display_decimal(rate),
            "cash_back_scope": scope,
            "annual_fee": display_decimal(fee),
            "required_subscription": required_subscription,
            "subscription_status": state,
            "minimum_credit_score": display_decimal(minimum_score),
            "source_notes": source_notes,
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
    output(recommendations, excluded, errors)


if __name__ == "__main__":
    main()
