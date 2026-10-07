#!/usr/bin/env python3
"""Evaluate structured card-product criteria without making account changes.

Read one JSON request from stdin and emit a JSON response to stdout. See SKILL.md
for the public input schema. This module uses only the Python standard library.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def as_percent(value: Any) -> Optional[Decimal]:
    """Parse a numeric percentage or a string such as '1.5%' as Decimal."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        text = value.strip()
        match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*%?", text)
        if match:
            try:
                return Decimal(match.group(1))
            except InvalidOperation:
                return None
    return None


def as_number(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None


def evaluate_card(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    result = dict(card)
    failures: list[str] = []
    unknowns: list[str] = []
    passes: list[str] = []
    name = str(card.get("name", "Unnamed card"))

    desired_type = requirements.get("product_type")
    if desired_type is not None:
        actual_type = card.get("product_type")
        if actual_type is None:
            unknowns.append("product type is not documented")
        elif str(actual_type).casefold() != str(desired_type).casefold():
            failures.append(f"product type is {actual_type!r}, not requested {desired_type!r}")
        else:
            passes.append("requested product type")

    score_threshold = as_number(card.get("minimum_credit_score"))
    customer_score = as_number(customer.get("credit_score"))
    if score_threshold is not None:
        if customer_score is None:
            unknowns.append("customer credit score was not supplied")
        elif customer_score < score_threshold:
            failures.append(f"credit score {customer_score} is below documented minimum {score_threshold}")
        else:
            passes.append(f"credit score meets documented minimum {score_threshold}")

    checks = (
        ("max_foreign_transaction_fee_percent", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment_percent", "minimum payment percentage"),
    )
    for requirement_key, card_key, label in checks:
        maximum = as_percent(requirements.get(requirement_key))
        if maximum is None:
            continue
        actual = as_percent(card.get(card_key))
        if actual is None:
            unknowns.append(f"{label} is not documented")
        elif actual > maximum:
            failures.append(f"{label} {actual}% exceeds requested maximum {maximum}%")
        else:
            passes.append(f"{label} {actual}% is within requested maximum {maximum}%")

    required_virtual = requirements.get("requires_virtual_card_management")
    if required_virtual is True:
        virtual = card.get("virtual_card_management")
        if virtual is None:
            unknowns.append("virtual-card-management availability is not documented")
        elif virtual is not True:
            failures.append("virtual-card management is not available")
        else:
            passes.append("virtual-card management is available")
    elif required_virtual is False:
        # An explicit non-requirement needs no product-side comparison.
        passes.append("virtual-card management is not required")

    required_memberships = card.get("required_memberships")
    if required_memberships is not None:
        if not isinstance(required_memberships, list):
            unknowns.append("documented membership requirement has invalid format")
        else:
            held = customer.get("memberships")
            if not isinstance(held, list):
                unknowns.append("customer memberships were not supplied")
            else:
                held_normalized = {str(item).casefold() for item in held}
                absent = [str(item) for item in required_memberships if str(item).casefold() not in held_normalized]
                if absent:
                    failures.append("missing required membership(s): " + ", ".join(absent))
                elif required_memberships:
                    passes.append("required membership(s) held")

    result["evaluation"] = {
        "card_name": name,
        "passed": passes,
        "failed": failures,
        "unknown": unknowns,
    }
    if failures:
        result["status"] = "not_qualified"
    elif unknowns:
        result["status"] = "needs_review"
    else:
        result["status"] = "qualified"
    return result


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        customer = payload.get("customer", {})
        requirements = payload.get("requirements", {})
        cards = payload.get("cards", [])
        if not isinstance(customer, dict) or not isinstance(requirements, dict) or not isinstance(cards, list):
            raise ValueError("customer and requirements must be objects and cards must be an array")
        if any(not isinstance(card, dict) for card in cards):
            raise ValueError("each cards entry must be an object")

        evaluated = [evaluate_card(card, customer, requirements) for card in cards]
        output = {
            "qualified": [card for card in evaluated if card["status"] == "qualified"],
            "not_qualified": [card for card in evaluated if card["status"] == "not_qualified"],
            "needs_review": [card for card in evaluated if card["status"] == "needs_review"],
            "notice": "A qualified result confirms only the supplied documented criteria; it is not an approval decision.",
        }
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"error": "invalid_input", "message": str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
