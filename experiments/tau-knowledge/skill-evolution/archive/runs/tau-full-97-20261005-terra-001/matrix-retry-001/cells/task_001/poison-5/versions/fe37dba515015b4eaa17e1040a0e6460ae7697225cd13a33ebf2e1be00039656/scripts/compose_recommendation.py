#!/usr/bin/env python3
"""Compose a conditional, evidence-grounded recommendation.

Read one JSON object from stdin and write one JSON object to stdout. This helper
never chooses a card; its card facts must already have been extracted and
verified from current supplied product documents. It performs no network,
account, file, or tool access.

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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

VALID_STATUSES = {"active", "inactive", "unknown", "not_required"}


def emit(message, errors):
    print(json.dumps({"message": message, "validation_errors": errors}, ensure_ascii=False))


def number(value, field, errors):
    if isinstance(value, bool) or value is None:
        errors.append(f"{field} must be a nonnegative number")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a nonnegative number")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(f"{field} must be a nonnegative finite number")
        return None
    return parsed


def rate_text(value):
    return format(value.normalize(), "f")


def money_text(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit("", [f"invalid JSON: {exc.msg}"])
        return
    if not isinstance(data, dict):
        emit("", ["top-level input must be an object"])
        return

    card = data.get("card")
    customer = data.get("customer")
    if not isinstance(card, dict):
        emit("", ["card must be an object"])
        return
    if not isinstance(customer, dict):
        emit("", ["customer must be an object"])
        return

    errors = []
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("card.name must be a nonempty string")
    rate = number(card.get("cash_back_rate_percent"), "card.cash_back_rate_percent", errors)
    fee = number(card.get("annual_fee"), "card.annual_fee", errors)
    if card.get("cash_back_scope") != "flat_all_eligible":
        errors.append("card.cash_back_scope must be flat_all_eligible for this composer")

    subscription = card.get("required_subscription")
    if subscription is not None and (not isinstance(subscription, str) or not subscription.strip()):
        errors.append("card.required_subscription must be a nonempty string or null")
    status = card.get("subscription_status")
    if status not in VALID_STATUSES:
        errors.append("card.subscription_status is invalid")
    if not subscription and status != "not_required":
        errors.append("subscription_status must be not_required when no subscription is required")

    minimum_raw = card.get("minimum_credit_score")
    minimum = None if minimum_raw is None else number(
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
        f"for your requested simple everyday cash back. It earns {rate_text(rate)}% cash back "
        f"on all eligible purchases and has a ${money_text(fee)} annual card fee."
    )
    if subscription:
        if status == "active" and context and context.strip():
            message += (
                f" It requires {subscription.strip()}. Because you report {context.strip()}, "
                "that appears to meet the subscription prerequisite."
            )
        elif status == "inactive":
            message += f" It requires {subscription.strip()}, which you report is not active."
        else:
            message += f" It requires {subscription.strip()}, so confirm that prerequisite is active."
    if minimum is not None:
        message += f" It also requires a minimum credit score of {rate_text(minimum)}."
        if not score_known:
            message += (
                " Since you do not know your score, check your score or eligibility before "
                "applying; eligibility and approval are not confirmed and remain subject to underwriting."
            )
        else:
            message += " Meeting that threshold does not guarantee approval; approval remains subject to underwriting."
    else:
        message += " Approval is not guaranteed and remains subject to underwriting."

    emit(message, [])


if __name__ == "__main__":
    main()
