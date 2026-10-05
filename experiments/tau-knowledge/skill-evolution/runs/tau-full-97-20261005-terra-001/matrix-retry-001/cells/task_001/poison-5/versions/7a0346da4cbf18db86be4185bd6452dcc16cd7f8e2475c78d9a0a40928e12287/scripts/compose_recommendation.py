#!/usr/bin/env python3
"""Compose conditional recommendation wording from already-verified facts.

Input and output schemas are documented in SKILL.md. This helper does not select
cards, retrieve evidence, access accounts, or decide eligibility.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

STATES = {"active", "inactive", "unknown", "not_required"}


def number(value, label, errors):
    if value is None or isinstance(value, bool):
        errors.append(f"{label} must be a nonnegative number")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a nonnegative number")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label} must be a nonnegative finite number")
        return None
    return result


def plain(value):
    return format(value.normalize(), "f")


def emit(message, errors):
    print(json.dumps({"message": message, "validation_errors": errors}, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit("", [f"invalid JSON: {exc.msg}"])
        return
    if not isinstance(data, dict) or not isinstance(data.get("card"), dict) or not isinstance(data.get("customer"), dict):
        emit("", ["card and customer must be objects"])
        return
    card, customer, errors = data["card"], data["customer"], []
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("card.name must be a nonempty string")
    rate = number(card.get("cash_back_rate_percent"), "card.cash_back_rate_percent", errors)
    fee = number(card.get("annual_fee"), "card.annual_fee", errors)
    if card.get("cash_back_scope") != "flat_all_eligible":
        errors.append("card.cash_back_scope must be flat_all_eligible")
    subscription = card.get("required_subscription")
    state = card.get("subscription_status")
    if subscription is not None and (not isinstance(subscription, str) or not subscription.strip()):
        errors.append("card.required_subscription must be a nonempty string or null")
    if state not in STATES:
        errors.append("card.subscription_status is invalid")
    if subscription is None and state != "not_required":
        errors.append("subscription_status must be not_required without a subscription")
    minimum = None if card.get("minimum_credit_score") is None else number(card.get("minimum_credit_score"), "card.minimum_credit_score", errors)
    known = customer.get("credit_score_known")
    if not isinstance(known, bool):
        errors.append("customer.credit_score_known must be boolean")
    context = customer.get("subscription_context")
    if context is not None and not isinstance(context, str):
        errors.append("customer.subscription_context must be a string or null")
    if errors:
        emit("", errors)
        return
    message = (f"Based on the documented terms, {name.strip()} is the leading documented fit for your requested simple everyday cash back. "
               f"It earns {plain(rate)}% cash back on all eligible purchases and has a ${format(fee.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), 'f')} annual card fee.")
    if subscription:
        if state == "active" and context and context.strip():
            message += f" It requires {subscription.strip()}. Because you report {context.strip()}, that appears to meet the subscription prerequisite, subject to confirmation."
        else:
            message += f" It requires {subscription.strip()}, so confirm that prerequisite is active."
    if minimum is not None:
        message += f" It also requires a minimum credit score of {plain(minimum)}."
        if not known:
            message += " Since you do not know your score, check your score or eligibility before applying; eligibility and approval are not confirmed and remain subject to underwriting."
        else:
            message += " Meeting that threshold does not guarantee approval; approval remains subject to underwriting."
    else:
        message += " Approval is not guaranteed and remains subject to underwriting."
    emit(message, [])


if __name__ == "__main__":
    main()
