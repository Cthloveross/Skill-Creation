#!/usr/bin/env python3
"""Evaluate structured card criteria without performing banking actions.

Read one JSON object from stdin and emit one JSON object on stdout. This module is
used by evaluate_documented_cards.py and may also be called directly as documented
in SKILL.md. It uses only the Python standard library.
"""

from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


def as_percent(value: Any) -> Optional[Decimal]:
    """Parse a numeric percentage or text such as ``1.5%``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*%?\s*", value)
        if match:
            try:
                return Decimal(match.group(1))
            except InvalidOperation:
                return None
    return None


def as_number(value: Any) -> Optional[Decimal]:
    """Parse a number, accepting incidental dollar signs and commas in source text."""
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

    desired_type = requirements.get("product_type")
    if desired_type is not None:
        actual_type = card.get("product_type")
        if actual_type is None:
            unknowns.append("product type is not documented")
        elif str(actual_type).casefold() != str(desired_type).casefold():
            failures.append(f"product type is {actual_type!r}, not requested {desired_type!r}")
        else:
            passes.append("requested product type")

    threshold = as_number(card.get("minimum_credit_score"))
    score = as_number(customer.get("credit_score"))
    if threshold is not None:
        if score is None:
            unknowns.append("customer credit score was not supplied")
        elif score < threshold:
            failures.append(f"credit score {score} is below documented minimum {threshold}")
        elif threshold == 0:
            passes.append("documentation states no credit-score requirement (minimum 0)")
        else:
            passes.append(f"credit score meets documented minimum {threshold}")

    for requirement_key, card_key, label in (
        ("max_foreign_transaction_fee_percent", "foreign_transaction_fee_percent", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment_percent", "minimum payment percentage"),
    ):
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

    if requirements.get("requires_virtual_card_management") is True:
        virtual = card.get("virtual_card_management")
        if virtual is None:
            unknowns.append("virtual-card-management availability is not documented")
        elif virtual is not True:
            failures.append("virtual-card management is not available")
        else:
            passes.append("virtual-card management is available")

    memberships = card.get("required_memberships")
    if memberships is not None:
        if not isinstance(memberships, list):
            unknowns.append("documented membership requirement has invalid format")
        else:
            held = customer.get("memberships")
            if not isinstance(held, list):
                unknowns.append("customer memberships were not supplied")
            else:
                held_set = {str(item).casefold() for item in held}
                absent = [str(item) for item in memberships if str(item).casefold() not in held_set]
                if absent:
                    failures.append("missing required membership(s): " + ", ".join(absent))
                elif memberships:
                    passes.append("required membership(s) held")

    result["evaluation"] = {"passed": passes, "failed": failures, "unknown": unknowns}
    result["status"] = "not_qualified" if failures else "needs_review" if unknowns else "qualified"
    return result


def evaluate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    customer = payload.get("customer", {})
    requirements = payload.get("requirements", {})
    cards = payload.get("cards", [])
    if not isinstance(customer, dict) or not isinstance(requirements, dict) or not isinstance(cards, list):
        raise ValueError("customer and requirements must be objects and cards must be an array")
    if any(not isinstance(card, dict) for card in cards):
        raise ValueError("each cards entry must be an object")
    evaluated = [evaluate_card(card, customer, requirements) for card in cards]
    return {
        "qualified": [card for card in evaluated if card["status"] == "qualified"],
        "not_qualified": [card for card in evaluated if card["status"] == "not_qualified"],
        "needs_review": [card for card in evaluated if card["status"] == "needs_review"],
        "notice": "A qualified result confirms only supplied documented criteria; it is not an approval decision.",
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        output = evaluate_payload(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"error": "invalid_input", "message": str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
