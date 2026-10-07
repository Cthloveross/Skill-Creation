#!/usr/bin/env python3
"""Evaluate supplied credit-card documents against stated shopping requirements.

Input: one JSON object on stdin with documents, customer, and requirements as
specified in SKILL.md. Output: one JSON object on stdout. This program uses only
provided text and does not perform banking or account actions.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal(value: Any) -> Decimal | None:
    """Convert a percentage/score input to Decimal without accepting booleans."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", "").replace("%", ""))
    except (InvalidOperation, AttributeError):
        return None


def display(value: Any) -> str:
    parsed = decimal(value)
    if parsed is None:
        return "unknown"
    text = format(parsed.normalize(), "f")
    return text if "." in text else text + ".0"


def first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if found:
            return found.group(1)
    return None


def add_fact(card: dict[str, Any], field: str, value: Any, source: str) -> None:
    """Add a product fact; mark differing document statements as ambiguous."""
    card.setdefault("sources", {}).setdefault(field, []).append(source)
    if field in card.get("ambiguous", []):
        return
    if field not in card:
        card[field] = value
    elif card[field] != value:
        card.pop(field, None)
        card.setdefault("ambiguous", []).append(field)


def product_name(title: str) -> str:
    """Titles conventionally begin with the product name before a colon."""
    return title.split(":", 1)[0].strip()


def extract_products(documents: list[Any]) -> list[dict[str, Any]]:
    products: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title = document.get("title")
        text = document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(text, str):
            continue

        name = product_name(title)
        card = products.setdefault(name, {"name": name, "sources": {}})
        source = str(document.get("document_id") or title)
        lowered_title = title.casefold()
        if "business" in lowered_title:
            add_fact(card, "product_type", "business", source)
        elif "card" in lowered_title:
            add_fact(card, "product_type", "personal", source)

        score = first_match(text, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?(?:credit\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)",
            r"applications?\s+should\s+meet\s+at\s+least\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            add_fact(card, "minimum_credit_score", decimal(score), source)

        foreign_fee = first_match(text, [
            r"foreign\s+transaction\s+fee[^:\n]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%"
        ])
        if foreign_fee is not None:
            add_fact(card, "foreign_fee", decimal(foreign_fee), source)

        minimum_payment = first_match(text, [
            r"minimum\s+(?:monthly\s+)?payment\s+is\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if minimum_payment is not None:
            add_fact(card, "minimum_payment", decimal(minimum_payment), source)

        virtual = first_match(text, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            add_fact(card, "virtual_cards", virtual.casefold() == "yes", source)

        membership = first_match(text, [
            r"([A-Za-z0-9+ -]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes"
        ])
        if membership:
            add_fact(card, "membership", membership.strip(), source)
    return list(products.values())


def evaluate(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    ambiguous = set(card.get("ambiguous", []))

    def required_field(field: str, condition: bool, good: str, bad: str, missing: str) -> None:
        if field in ambiguous or card.get(field) is None:
            unknown.append(missing)
        elif condition:
            passed.append(good)
        else:
            failed.append(bad)

    wanted_type = requirements.get("product_type")
    if wanted_type is not None:
        required_field(
            "product_type",
            str(card.get("product_type", "")).casefold() == str(wanted_type).casefold(),
            "requested product type",
            "wrong product type",
            "product type is undocumented",
        )

    score = decimal(customer.get("credit_score"))
    if score is not None:
        threshold = decimal(card.get("minimum_credit_score"))
        if "minimum_credit_score" in ambiguous or threshold is None:
            unknown.append("minimum credit-score requirement is undocumented")
        elif score < threshold:
            failed.append("credit score is below the documented minimum")
        else:
            passed.append("no credit-score requirement" if threshold == 0 else "credit score meets documented minimum")

    comparisons = (
        ("max_foreign_transaction_fee_percent", "foreign_fee", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment", "minimum payment"),
    )
    for requirement_field, product_field, label in comparisons:
        ceiling = decimal(requirements.get(requirement_field))
        actual = decimal(card.get(product_field))
        if ceiling is None:
            continue
        if product_field in ambiguous or actual is None:
            unknown.append(label + " is undocumented")
        elif actual <= ceiling:
            passed.append(label + " is within requested maximum")
        else:
            failed.append(label + " exceeds requested maximum")

    if requirements.get("requires_virtual_card_management") is True:
        required_field(
            "virtual_cards",
            card.get("virtual_cards") is True,
            "virtual-card management available",
            "virtual-card management unavailable",
            "virtual-card management is undocumented",
        )

    membership = card.get("membership")
    if membership:
        held = customer.get("memberships", [])
        if not isinstance(held, list):
            unknown.append("customer membership status is invalid")
        elif str(membership).casefold() in {str(item).casefold() for item in held}:
            passed.append("required membership held")
        else:
            failed.append("required membership is not held")

    status = "not_qualified" if failed else "needs_review" if unknown else "qualified"
    return {**card, "status": status, "evaluation": {"passed": passed, "failed": failed, "unknown": unknown}}


def build_match_message(matches: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ", ".join(card["name"] for card in matches)
    verb = "is" if len(matches) == 1 else "are"
    paragraphs = [f"Based on the supplied product documents, {names} {verb} a confirmed match for the published criteria you gave."]
    score = decimal(customer.get("credit_score"))

    for card in matches:
        terms: list[str] = []
        threshold = decimal(card.get("minimum_credit_score"))
        if threshold == 0:
            score_note = ""
            if score is not None:
                score_note = f", so your stated score of {display(score)} does not exclude you from applying"
            terms.append("it has no credit-score requirement (published minimum: 0)" + score_note)
        elif threshold is not None:
            terms.append("its documented minimum credit score is " + display(threshold))

        foreign_cap = requirements.get("max_foreign_transaction_fee_percent")
        if foreign_cap is not None:
            terms.append(
                f"its foreign transaction fee is {display(card['foreign_fee'])}%, within your {display(foreign_cap)}% maximum"
            )

        payment_cap = requirements.get("max_minimum_payment_percent")
        if payment_cap is not None:
            terms.append(
                f"its minimum monthly payment is {display(card['minimum_payment'])}% of the outstanding balance, within your {display(payment_cap)}% maximum"
            )

        if requirements.get("requires_virtual_card_management") is True:
            terms.append("virtual-card management is available and can help organize spending")
        paragraphs.append(card["name"] + ": " + "; ".join(terms) + ".")

    if customer.get("income") is not None:
        paragraphs.append("No applicable documented income threshold was used in this comparison.")
    paragraphs.append("This comparison of published criteria does not guarantee approval.")
    return "\n\n".join(paragraphs)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
            raise ValueError("documents must be an array")
        customer = payload.get("customer", {})
        requirements = payload.get("requirements", {})
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")

        evaluated = [evaluate(card, customer, requirements) for card in extract_products(payload["documents"])]
        qualified = [card for card in evaluated if card["status"] == "qualified"]
        if qualified:
            output = {
                "status": "confirmed_match",
                "message": build_match_message(qualified, customer, requirements),
                "qualified": qualified,
                "evaluated_cards": evaluated,
            }
        else:
            status = "needs_review" if any(card["status"] == "needs_review" for card in evaluated) else "no_confirmed_match"
            output = {
                "status": status,
                "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.",
                "qualified": [],
                "evaluated_cards": evaluated,
            }
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"status": "invalid_input", "message": str(exc), "qualified": [], "evaluated_cards": []}
    print(json.dumps(output, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
