#!/usr/bin/env python3
"""Compose a conditional, evidence-grounded recommendation.

Read one JSON object from stdin and write one JSON object to stdout. This helper
never chooses a card and must receive a card already selected from supplied terms.
It performs no network, account, file, or tool access.

Input schema:
{
  "card": {
    "name": "string",
    "cash_back_rate_percent": "number",
    "cash_back_scope": "flat_all_eligible",
    "annual_fee": "number",
    "required_subscription": "string or null",
    "subscription_status": "active|inactive|unknown|not_required",
    "minimum_credit_score": "number or null"
  },
  "customer": {
    "subscription_context": "string or null",
    "credit_score_known": false
  }
}

Output schema:
{"message": "string", "validation_errors": ["string"]}
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def numeric_text(value, field, errors):
    if isinstance(value, bool) or value is None:
        errors.append(f"{field} must be a nonnegative number")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a nonnegative number")
        return None
    if not number.is_finite() or number < 0:
        errors.append(f"{field} must be a nonnegative finite number")
        return None
    return format(number.normalize(), "f")


def emit(message, errors):
    print(json.dumps({"message": message, "validation_errors": errors}, ensure_ascii=False))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit("", [f"invalid JSON: {exc.msg}"])
        return
    if not isinstance(data, dict):
        emit("", ["top-level input must be an object"])
        return

    errors = []
    card = data.get("card")
    customer = data.get("customer")
    if not isinstance(card, dict):
        emit("", ["card must be an object"])
        return
    if not isinstance(customer, dict):
        emit("", ["customer must be an object"])
        return

    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("card.name must be a nonempty string")
    rate = numeric_text(card.get("cash_back_rate_percent"), "card.cash_back_rate_percent", errors)
    fee = numeric_text(card.get("annual_fee"), "card.annual_fee", errors)
    scope = card.get("cash_back_scope")
    if scope != "flat_all_eligible":
        errors.append("card.cash_back_scope must be flat_all_eligible for this composer")
    subscription = card.get("required_subscription")
    if subscription is not None and (not isinstance(subscription, str) or not subscription.strip()):
        errors.append("card.required_subscription must be a nonempty string or null")
    minimum_raw = card.get("minimum_credit_score")
    minimum = None if minimum_raw is None else numeric_text(
        minimum_raw, "card.minimum_credit_score", errors
    )
    score_known = customer.get("credit_score_known")
    if not isinstance(score_known, bool):
        errors.append("customer.credit_score_known must be boolean")
    context = customer.get("subscription_context")
    if context is not None and not isinstance(context, str):
        errors.append("customer.subscription_context must be a string or null")

    if errors:
        emit("", errors)
        return

    message = (
        f"Based on the documented terms, {name.strip()} is the leading documented fit "
        f"for your requested simple everyday cash back. It earns {rate}% cash back "
        f"on all eligible purchases and has a ${fee} annual card fee."
    )
    if subscription:
        if context:
            message += (
                f" It requires {subscription.strip()}. Because you report {context.strip()}, "
                "that appears to meet the subscription prerequisite."
            )
        else:
            message += f" It requires {subscription.strip()}, so confirm that prerequisite is active."
    if minimum:
        message += f" It also requires a minimum credit score of {minimum}."
        if not score_known:
            message += (
                " Since you do not know your score, check your score or eligibility before "
                "applying; eligibility and approval are not confirmed and remain subject to underwriting."
            )
    elif not score_known:
        message += " Approval is not guaranteed and remains subject to underwriting."
    emit(message, [])


if __name__ == "__main__":
    main()
