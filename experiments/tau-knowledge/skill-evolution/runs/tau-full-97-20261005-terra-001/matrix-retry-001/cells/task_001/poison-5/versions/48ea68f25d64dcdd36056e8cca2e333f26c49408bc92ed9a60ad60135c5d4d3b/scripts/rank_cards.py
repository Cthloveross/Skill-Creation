#!/usr/bin/env python3
"""Rank already-extracted card facts against explicit preferences.

Reads one JSON object from stdin and emits one JSON object on stdout:
{"recommendations": [...], "excluded": [...], "validation_errors": [...]}.
No network, account, file, or tool access is performed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

SCOPES = {"flat_all_eligible", "category_or_mixed", "unknown"}
STATUSES = {"active", "inactive", "unknown"}


def emit(recommendations, excluded, errors):
    print(json.dumps({"recommendations": recommendations, "excluded": excluded,
                      "validation_errors": errors}, ensure_ascii=False))


def decimal(value, field, errors, required=True):
    if value is None:
        if required:
            errors.append(f"{field} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(f"{field} must be a nonnegative finite number")
        return None
    return parsed


def show(value):
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
        errors.append("preferences must be an object")
        preferences = {}
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []

    simple = preferences.get("simple_flat_cashback")
    if not isinstance(simple, bool):
        errors.append("preferences.simple_flat_cashback must be boolean")
        simple = False
    max_fee = decimal(preferences.get("max_annual_fee"), "preferences.max_annual_fee", errors)
    score_raw = preferences.get("credit_score")
    score = None if score_raw is None else decimal(score_raw, "preferences.credit_score", errors)

    statuses = preferences.get("subscription_status", {})
    if not isinstance(statuses, dict):
        errors.append("preferences.subscription_status must be an object")
        statuses = {}
    clean_statuses = {}
    for name, status in statuses.items():
        if not isinstance(name, str) or not name.strip() or status not in STATUSES:
            errors.append("subscription_status has an invalid name or state")
        else:
            clean_statuses[name.strip()] = status

    recommendations, excluded = [], []
    for i, card in enumerate(cards):
        prefix = f"cards[{i}]"
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
        elif isinstance(subscription, str):
            subscription = subscription.strip()
        minimum_raw = card.get("min_credit_score")
        minimum = None if minimum_raw is None else decimal(minimum_raw, f"{prefix}.min_credit_score", errors)

        reasons, conditions = [], []
        if rate is None or fee is None:
            reasons.append("cash-back rate or annual card fee is unverified")
        if max_fee is not None and fee is not None and fee > max_fee:
            reasons.append("annual card fee exceeds the stated maximum")
        if simple and scope == "category_or_mixed":
            reasons.append("rewards are category-based or mixed, not the requested flat rate")
        if simple and scope == "unknown":
            conditions.append("confirm whether the rate applies to all eligible purchases")

        state = "not_required" if not subscription else clean_statuses.get(subscription, "unknown")
        if state == "inactive":
            reasons.append("required subscription is known inactive")
        elif state == "unknown":
            conditions.append(f"confirm active required subscription: {subscription}")
        if minimum is not None:
            if score is None:
                conditions.append(f"meet the minimum credit score of {show(minimum)}")
            elif score < minimum:
                reasons.append(f"credit score is below the minimum of {show(minimum)}")

        record = {"name": name.strip(), "cash_back_rate_percent": show(rate),
                  "cash_back_scope": scope, "annual_fee": show(fee),
                  "required_subscription": subscription, "subscription_status": state,
                  "minimum_credit_score": show(minimum)}
        if reasons:
            record["reasons"] = reasons
            excluded.append(record)
        else:
            record["conditions"] = conditions
            record["eligibility"] = "conditional" if conditions else "eligible"
            recommendations.append(record)

    recommendations.sort(key=lambda x: (-Decimal(x["cash_back_rate_percent"] or "0"),
                                         0 if x["eligibility"] == "eligible" else 1,
                                         x["name"].casefold()))
    excluded.sort(key=lambda x: x["name"].casefold())
    emit(recommendations, excluded, errors)


if __name__ == "__main__":
    main()
