#!/usr/bin/env python3
"""Rank already-extracted card facts and compose conditional advice.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON
object to stdout. It performs no retrieval, network access, account access, or
eligibility decision.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
STATES = {"active", "inactive", "unknown"}


def number(value, label, errors, required=True):
    if value is None:
        if required:
            errors.append(label + " is required")
        return None
    if isinstance(value, bool):
        errors.append(label + " must be numeric")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(label + " must be numeric")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(label + " must be a nonnegative finite number")
        return None
    return parsed


def show(value):
    return format(value.normalize(), "f")


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def emit(leading, excluded, message, errors):
    print(json.dumps({
        "leading": leading,
        "excluded": excluded,
        "message": message,
        "validation_errors": errors,
    }, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit(None, [], "", ["invalid JSON: " + exc.msg])
        return

    if not isinstance(data, dict):
        emit(None, [], "", ["top-level input must be an object"])
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

    simple_flat = preferences.get("simple_flat_cashback")
    if not isinstance(simple_flat, bool):
        errors.append("preferences.simple_flat_cashback must be boolean")
        simple_flat = False
    maximum_fee = number(
        preferences.get("max_annual_fee"),
        "preferences.max_annual_fee",
        errors,
    )
    score = None if preferences.get("credit_score") is None else number(
        preferences.get("credit_score"),
        "preferences.credit_score",
        errors,
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
    for index, raw in enumerate(cards):
        prefix = "cards[{}]".format(index)
        if not isinstance(raw, dict):
            errors.append(prefix + " must be an object")
            continue

        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".name must be a nonempty string")
            continue
        name = name.strip()
        rate = number(raw.get("cash_back_rate"), prefix + ".cash_back_rate", errors)
        fee = number(raw.get("annual_fee"), prefix + ".annual_fee", errors)
        scope = raw.get("cash_back_scope")
        if scope not in SCOPES:
            errors.append(prefix + ".cash_back_scope is invalid")
            scope = "unknown"

        subscription = raw.get("required_subscription")
        if subscription is not None and (
            not isinstance(subscription, str) or not subscription.strip()
        ):
            errors.append(prefix + ".required_subscription must be a nonempty string or null")
            subscription = None
        if isinstance(subscription, str):
            subscription = subscription.strip()

        minimum = None if raw.get("minimum_credit_score") is None else number(
            raw.get("minimum_credit_score"),
            prefix + ".minimum_credit_score",
            errors,
        )

        reasons = []
        conditions = []
        if rate is None or fee is None:
            reasons.append("rate or standard annual card fee is unverified")
        if maximum_fee is not None and fee is not None and fee > maximum_fee:
            reasons.append("standard annual card fee exceeds the stated maximum")
        if simple_flat and scope == "category_or_mixed":
            reasons.append("category or mixed rewards do not match the requested flat rate")
        if simple_flat and scope == "unknown":
            conditions.append("confirm reward scope")

        state = "not_required" if subscription is None else statuses.get(subscription, "unknown")
        if state != "not_required" and state not in STATES:
            errors.append("subscription state for {} is invalid".format(subscription))
            state = "unknown"
        if state == "inactive":
            reasons.append("required subscription is known inactive")
        elif state == "unknown":
            conditions.append("confirm active required subscription: " + subscription)

        if minimum is not None:
            if score is None:
                conditions.append("verify minimum credit score of " + show(minimum))
            elif score < minimum:
                reasons.append(
                    "credit score is below documented minimum of " + show(minimum)
                )

        record = {
            "name": name,
            "cash_back_rate_percent": show(rate) if rate is not None else None,
            "cash_back_scope": scope,
            "annual_fee": show(fee) if fee is not None else None,
            "required_subscription": subscription,
            "subscription_status": state,
            "minimum_credit_score": show(minimum) if minimum is not None else None,
        }
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            retained.append(record)

    retained.sort(
        key=lambda item: (
            -Decimal(item["cash_back_rate_percent"]),
            0 if item["cash_back_scope"] == "flat_all_eligible" else 1,
            item["name"].casefold(),
        )
    )
    excluded.sort(key=lambda item: item["name"].casefold())

    if errors or not retained:
        emit(retained[0] if retained else None, excluded, "", errors)
        return

    leading = retained[0]
    scope_text = (
        "all eligible purchases"
        if leading["cash_back_scope"] == "flat_all_eligible"
        else "the documented eligible purchases"
    )
    message = (
        "Based on the documented terms, {name} is the leading documented fit for "
        "your requested simple everyday cash back. It earns {rate}% cash back on "
        "{scope} and has a ${fee} annual card fee."
    ).format(
        name=leading["name"],
        rate=leading["cash_back_rate_percent"],
        scope=scope_text,
        fee=money(Decimal(leading["annual_fee"])),
    )

    if leading["required_subscription"]:
        message += " It requires {}.".format(leading["required_subscription"])
        if leading["subscription_status"] == "active" and context and context.strip():
            message += (
                " Because you report {}, that appears to meet the subscription "
                "prerequisite, subject to confirmation."
            ).format(context.strip())
        else:
            message += " Confirm that this subscription prerequisite is active."

    if leading["minimum_credit_score"] is not None:
        message += " It also requires a minimum credit score of {}.".format(
            leading["minimum_credit_score"]
        )
        if score is None:
            message += (
                " Since you do not know your score, check your score or eligibility "
                "before applying; eligibility and approval are not confirmed and "
                "remain subject to underwriting."
            )
        else:
            message += (
                " Meeting that threshold does not guarantee approval; approval "
                "remains subject to underwriting."
            )
    else:
        message += " Approval is not guaranteed and remains subject to underwriting."

    emit(leading, excluded, message, errors)


if __name__ == "__main__":
    main()
