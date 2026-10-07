#!/usr/bin/env python3
"""Rank already-extracted card facts against explicit customer preferences.

Reads one JSON object from stdin and emits:
{"recommendations": [...], "excluded": [...], "validation_errors": [...]}.
It does not retrieve documents or decide approval.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
STATES = {"active", "inactive", "unknown"}


def decimal(value, label, errors, required=True):
    if value is None:
        if required:
            errors.append(f"{label} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be numeric")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a nonnegative finite number")
        return None
    return result


def render(value):
    if value is None:
        return None
    text = format(value.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"recommendations": [], "excluded": [], "validation_errors": [f"invalid JSON: {exc.msg}"]}))
        return
    errors, recommendations, excluded = [], [], []
    if not isinstance(data, dict):
        print(json.dumps({"recommendations": [], "excluded": [], "validation_errors": ["top-level input must be an object"]}))
        return
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
        simple = False
        errors.append("preferences.simple_flat_cashback must be boolean")
    max_fee = decimal(prefs.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    score = None if prefs.get("credit_score") is None else decimal(prefs.get("credit_score"), "preferences.credit_score", errors)
    status_map = prefs.get("subscription_status", {})
    if not isinstance(status_map, dict):
        status_map = {}
        errors.append("preferences.subscription_status must be an object")

    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        rate = decimal(card.get("cash_back_rate"), f"{prefix}.cash_back_rate", errors)
        fee = decimal(card.get("annual_fee"), f"{prefix}.annual_fee", errors)
        scope = card.get("cash_back_scope")
        if scope not in SCOPES:
            errors.append(f"{prefix}.cash_back_scope is invalid")
            scope = "unknown"
        subscription = card.get("required_subscription")
        if subscription is not None and (not isinstance(subscription, str) or not subscription.strip()):
            errors.append(f"{prefix}.required_subscription must be a nonempty string or null")
            subscription = None
        if isinstance(subscription, str):
            subscription = subscription.strip()
        minimum = None if card.get("min_credit_score") is None else decimal(card.get("min_credit_score"), f"{prefix}.min_credit_score", errors)
        reasons, conditions = [], []
        if rate is None or fee is None:
            reasons.append("cash-back rate or annual card fee is unverified")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual card fee exceeds the stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("rewards are category-based or mixed, not the requested flat rate")
        if simple and scope == "unknown":
            conditions.append("confirm whether the rate applies to all eligible purchases")
        state = "not_required" if subscription is None else status_map.get(subscription, "unknown")
        if state not in STATES and state != "not_required":
            errors.append(f"subscription state for {subscription} is invalid")
            state = "unknown"
        if state == "inactive":
            reasons.append("required subscription is known inactive")
        elif state == "unknown":
            conditions.append(f"confirm active required subscription: {subscription}")
        if minimum is not None:
            if score is None:
                conditions.append(f"meet the minimum credit score of {render(minimum)}")
            elif score < minimum:
                reasons.append(f"credit score is below the minimum of {render(minimum)}")
        record = {"name": name.strip(), "cash_back_rate_percent": render(rate), "cash_back_scope": scope, "annual_fee": render(fee), "required_subscription": subscription, "subscription_status": state, "minimum_credit_score": render(minimum)}
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            record["eligibility"] = "conditional" if conditions else "eligible"
            recommendations.append(record)
    recommendations.sort(key=lambda x: (-Decimal(x["cash_back_rate_percent"] or "0"), 0 if x["eligibility"] == "eligible" else 1, x["name"].casefold()))
    excluded.sort(key=lambda x: x["name"].casefold())
    print(json.dumps({"recommendations": recommendations, "excluded": excluded, "validation_errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
