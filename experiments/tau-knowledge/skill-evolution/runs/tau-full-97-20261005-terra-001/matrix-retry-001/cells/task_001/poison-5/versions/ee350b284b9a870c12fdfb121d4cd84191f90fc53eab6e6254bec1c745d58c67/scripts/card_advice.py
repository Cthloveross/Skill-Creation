#!/usr/bin/env python3
"""Rank already-extracted card facts and compose conditional advice.

Reads the JSON schema in SKILL.md from stdin and writes one JSON object to stdout.
It performs no retrieval, network access, account access, or eligibility decision.
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
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(label + " must be numeric")
        return None
    if not value.is_finite() or value < 0:
        errors.append(label + " must be a nonnegative finite number")
        return None
    return value


def show(value):
    return format(value.normalize(), "f")


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def output(leading, excluded, message, errors):
    print(json.dumps({"leading": leading, "excluded": excluded,
                      "message": message, "validation_errors": errors},
                     ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output(None, [], "", ["invalid JSON: " + exc.msg])
        return
    if not isinstance(data, dict):
        output(None, [], "", ["top-level input must be an object"])
        return
    errors = []
    prefs = data.get("preferences")
    cards = data.get("cards")
    if not isinstance(prefs, dict):
        prefs = {}
        errors.append("preferences must be an object")
    if not isinstance(cards, list):
        cards = []
        errors.append("cards must be an array")
    simple = prefs.get("simple_flat_cashback")
    if not isinstance(simple, bool):
        errors.append("preferences.simple_flat_cashback must be boolean")
        simple = False
    maximum = number(prefs.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    score = None if prefs.get("credit_score") is None else number(
        prefs.get("credit_score"), "preferences.credit_score", errors)
    statuses = prefs.get("subscription_status", {})
    if not isinstance(statuses, dict):
        statuses = {}
        errors.append("preferences.subscription_status must be an object")
    context = prefs.get("subscription_context")
    if context is not None and not isinstance(context, str):
        errors.append("preferences.subscription_context must be a string or null")
        context = None

    retained, excluded = [], []
    for i, raw in enumerate(cards):
        prefix = "cards[{}]".format(i)
        if not isinstance(raw, dict):
            errors.append(prefix + " must be an object")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".name must be a nonempty string")
            continue
        rate = number(raw.get("cash_back_rate"), prefix + ".cash_back_rate", errors)
        fee = number(raw.get("annual_fee"), prefix + ".annual_fee", errors)
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
        minimum = None if raw.get("minimum_credit_score") is None else number(
            raw.get("minimum_credit_score"), prefix + ".minimum_credit_score", errors)
        reasons, conditions = [], []
        if rate is None or fee is None:
            reasons.append("rate or standard annual card fee is unverified")
        if maximum is not None and fee is not None and fee > maximum:
            reasons.append("standard annual card fee exceeds the stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("category or mixed rewards do not match the requested flat rate")
        if simple and scope == "unknown":
            conditions.append("confirm reward scope")
        state = "not_required" if subscription is None else statuses.get(subscription, "unknown")
        if state not in STATES and state != "not_required":
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
                reasons.append("credit score is below documented minimum of " + show(minimum))
        record = {"name": name.strip(), "cash_back_rate_percent": show(rate) if rate is not None else None,
                  "cash_back_scope": scope, "annual_fee": show(fee) if fee is not None else None,
                  "required_subscription": subscription, "subscription_status": state,
                  "minimum_credit_score": show(minimum) if minimum is not None else None}
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            retained.append(record)

    retained.sort(key=lambda item: (-Decimal(item["cash_back_rate_percent"]),
                                    0 if item["cash_back_scope"] == "flat_all_eligible" else 1,
                                    item["name"].casefold()))
    excluded.sort(key=lambda item: item["name"].casefold())
    if not retained or errors:
        output(retained[0] if retained else None, excluded, "", errors)
        return
    lead = retained[0]
    scope_text = "all eligible purchases" if lead["cash_back_scope"] == "flat_all_eligible" else "the documented eligible purchases"
    text = ("Based on the documented terms, {name} is the leading documented fit for your requested simple everyday cash back. "
            "It earns {rate}% cash back on {scope} and has a ${fee} annual card fee.").format(
                name=lead["name"], rate=lead["cash_back_rate_percent"], scope=scope_text,
                fee=money(Decimal(lead["annual_fee"])))
    if lead["required_subscription"]:
        text += " It requires {}.".format(lead["required_subscription"])
        if lead["subscription_status"] == "active" and context and context.strip():
            text += " Because you report {}, that appears to meet the subscription prerequisite, subject to confirmation.".format(context.strip())
        else:
            text += " Confirm that this subscription prerequisite is active."
    if lead["minimum_credit_score"] is not None:
        text += " It also requires a minimum credit score of {}.".format(lead["minimum_credit_score"])
        if score is None:
            text += " Since you do not know your score, check your score or eligibility before applying; eligibility and approval are not confirmed and remain subject to underwriting."
        else:
            text += " Meeting that threshold does not guarantee approval; approval remains subject to underwriting."
    else:
        text += " Approval is not guaranteed and remains subject to underwriting."
    output(lead, excluded, text, errors)


if __name__ == "__main__":
    main()
