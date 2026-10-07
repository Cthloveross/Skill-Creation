#!/usr/bin/env python3
"""Rank already-extracted card terms and draft conditional informational advice.

Input and output JSON schemas are documented in SKILL.md. This program performs
no retrieval, account access, credit decision, application, or banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
STATES = {"active", "inactive", "unknown"}


def decimal(value, field, errors, required=True):
    if value is None:
        if required:
            errors.append(field + " is required")
        return None
    if isinstance(value, bool):
        errors.append(field + " must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(field + " must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(field + " must be a nonnegative finite number")
        return None
    return result


def text_number(value):
    return format(value.normalize(), "f")


def emit(leading=None, excluded=None, message="", errors=None):
    print(json.dumps({
        "leading": leading,
        "excluded": excluded or [],
        "message": message,
        "validation_errors": errors or [],
    }, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit(errors=["invalid JSON: " + exc.msg])
        return
    if not isinstance(data, dict):
        emit(errors=["top-level input must be an object"])
        return

    errors = []
    preferences = data.get("preferences")
    cards = data.get("cards")
    if not isinstance(preferences, dict):
        preferences = {}
        errors.append("preferences must be an object")
    if not isinstance(cards, list):
        cards = []
        errors.append("cards must be an array")

    flat_preference = preferences.get("simple_flat_cashback")
    if not isinstance(flat_preference, bool):
        errors.append("preferences.simple_flat_cashback must be boolean")
        flat_preference = False
    max_fee = decimal(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    credit_score = None if preferences.get("credit_score") is None else decimal(
        preferences.get("credit_score"), "preferences.credit_score", errors
    )
    statuses = preferences.get("subscription_status", {})
    if not isinstance(statuses, dict):
        statuses = {}
        errors.append("preferences.subscription_status must be an object")
    context = preferences.get("subscription_context")
    if context is not None and not isinstance(context, str):
        errors.append("preferences.subscription_context must be a string or null")
        context = None

    retained = []
    excluded = []
    for i, raw in enumerate(cards):
        prefix = "cards[{}]".format(i)
        if not isinstance(raw, dict):
            errors.append(prefix + " must be an object")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".name must be a nonempty string")
            continue
        name = name.strip()
        rate = decimal(raw.get("cash_back_rate"), prefix + ".cash_back_rate", errors)
        fee = decimal(raw.get("annual_fee"), prefix + ".annual_fee", errors)
        scope = raw.get("cash_back_scope")
        if scope not in SCOPES:
            errors.append(prefix + ".cash_back_scope is invalid")
            scope = "unknown"
        subscription = raw.get("required_subscription")
        if subscription is not None and (not isinstance(subscription, str) or not subscription.strip()):
            errors.append(prefix + ".required_subscription must be a nonempty string or null")
            subscription = None
        if isinstance(subscription, str):
            subscription = subscription.strip()
        minimum = None if raw.get("minimum_credit_score") is None else decimal(
            raw.get("minimum_credit_score"), prefix + ".minimum_credit_score", errors
        )

        reasons = []
        conditions = []
        if rate is None or fee is None:
            reasons.append("documented rate or standard annual card fee is missing")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("standard annual card fee exceeds stated maximum")
        if flat_preference and scope == "category_or_mixed":
            reasons.append("category or mixed rewards do not match requested flat rate")
        if flat_preference and scope == "unknown":
            conditions.append("confirm reward scope")

        state = "not_required"
        if subscription is not None:
            state = statuses.get(subscription, "unknown")
            if state not in STATES:
                errors.append("subscription state for {} is invalid".format(subscription))
                state = "unknown"
            if state == "inactive":
                reasons.append("required subscription is known inactive")
            elif state == "unknown":
                conditions.append("confirm active required subscription: " + subscription)
        if minimum is not None:
            if credit_score is None:
                conditions.append("verify minimum credit score of " + text_number(minimum))
            elif credit_score < minimum:
                reasons.append("credit score is below documented minimum of " + text_number(minimum))

        record = {
            "name": name,
            "cash_back_rate_percent": text_number(rate) if rate is not None else None,
            "cash_back_scope": scope,
            "annual_fee": text_number(fee) if fee is not None else None,
            "required_subscription": subscription,
            "minimum_credit_score": text_number(minimum) if minimum is not None else None,
            "conditions": conditions,
        }
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            retained.append(record)

    retained.sort(key=lambda card: (
        -Decimal(card["cash_back_rate_percent"]),
        0 if card["cash_back_scope"] == "flat_all_eligible" else 1,
        card["name"].casefold(),
    ))
    excluded.sort(key=lambda card: card["name"].casefold())
    if errors or not retained:
        emit(retained[0] if retained else None, excluded, "", errors)
        return

    leading = retained[0]
    scope = "all eligible purchases" if leading["cash_back_scope"] == "flat_all_eligible" else "documented eligible purchases"
    message = (
        "Based on the documented terms, {name} is the leading fit for your requested "
        "simple everyday cash back. It earns {rate}% cash back on {scope} and has a "
        "${fee} annual card fee."
    ).format(name=leading["name"], rate=leading["cash_back_rate_percent"], scope=scope,
             fee=format(Decimal(leading["annual_fee"]), ".2f"))
    if leading["required_subscription"]:
        message += " It requires {}.".format(leading["required_subscription"])
        if statuses.get(leading["required_subscription"]) == "active" and context and context.strip():
            message += " Because you report {}, that appears to meet the subscription prerequisite, subject to confirmation.".format(context.strip())
        else:
            message += " Confirm that the subscription prerequisite is active."
    if leading["minimum_credit_score"] is not None:
        message += " It also requires a minimum credit score of {}.".format(leading["minimum_credit_score"])
        if credit_score is None:
            message += " Since you do not know your score, check your score or eligibility before applying; eligibility and approval are not confirmed and remain subject to underwriting."
        else:
            message += " Meeting that threshold does not guarantee approval; approval remains subject to underwriting."
    else:
        message += " Approval is not guaranteed and remains subject to underwriting."
    emit(leading, excluded, message, errors)


if __name__ == "__main__":
    main()
