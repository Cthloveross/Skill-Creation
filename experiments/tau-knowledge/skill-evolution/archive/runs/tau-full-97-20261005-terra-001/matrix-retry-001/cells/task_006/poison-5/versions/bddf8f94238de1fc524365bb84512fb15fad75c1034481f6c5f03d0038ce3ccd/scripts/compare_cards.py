#!/usr/bin/env python3
"""Compare supplied card documents against explicit shopping requirements.

Input is one JSON object on stdin as documented in SKILL.md. Output is one JSON
object on stdout. The program reads only supplied document text and never makes
banking, account, or network calls.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def number(value: Any) -> Decimal | None:
    """Parse a numeric score or percentage without accepting booleans."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", "").replace("%", ""))
    except (InvalidOperation, AttributeError):
        return None


def shown(value: Any) -> str:
    parsed = number(value)
    if parsed is None:
        return "unknown"
    text = format(parsed.normalize(), "f")
    return text if "." in text else text + ".0"


def find(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
    return None


def product_name(title: str) -> str:
    return title.split(":", 1)[0].strip()


def set_fact(card: dict[str, Any], field: str, value: Any, source: str) -> None:
    """Set a fact, retaining a conflict rather than selecting one unsupported value."""
    card.setdefault("sources", {}).setdefault(field, []).append(source)
    if field in card.get("ambiguous", set()):
        return
    if field not in card:
        card[field] = value
    elif card[field] != value:
        card.pop(field, None)
        card.setdefault("ambiguous", set()).add(field)


def extract(documents: list[Any]) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, text = document.get("title"), document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(text, str):
            continue
        name = product_name(title)
        card = cards.setdefault(name, {"name": name, "sources": {}, "ambiguous": set()})
        source = str(document.get("document_id") or title)
        title_and_id = (title + " " + source).casefold()
        set_fact(card, "product_type", "business" if "business" in title_and_id else "personal", source)

        score = find(text, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+(?:required|requirement|to\s+apply))*\s*(?:is|:|of)?\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)",
            r"(?:applications?\s+should\s+meet\s+at\s+least|score\s+of\s+at\s+least)\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            set_fact(card, "minimum_credit_score", number(score), source)

        foreign_fee = find(text, [
            r"foreign\s+transaction\s+fee[^\n:]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"foreign\s+transaction\s+fee[^\n0-9]{0,50}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if foreign_fee is not None:
            set_fact(card, "foreign_fee", number(foreign_fee), source)

        payment = find(text, [
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*(?:is|:)?\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment[^\n0-9]{0,50}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if payment is not None:
            set_fact(card, "minimum_payment", number(payment), source)

        virtual = find(text, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+available\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            set_fact(card, "virtual_cards", virtual.casefold() == "yes", source)

        membership = find(text, [
            r"([A-Za-z0-9+ -]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes"
        ])
        if membership is not None:
            set_fact(card, "membership", membership.strip(), source)

    result: list[dict[str, Any]] = []
    for card in cards.values():
        card["ambiguous"] = sorted(card["ambiguous"])
        result.append(card)
    return result


def evaluate(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    ambiguous = set(card.get("ambiguous", []))

    def assess(field: str, condition: bool, yes: str, no: str, absent: str) -> None:
        if field in ambiguous or field not in card or card.get(field) is None:
            unknown.append(absent)
        elif condition:
            passed.append(yes)
        else:
            failed.append(no)

    requested_type = requirements.get("product_type")
    if requested_type is not None:
        assess(
            "product_type",
            str(card.get("product_type", "")).casefold() == str(requested_type).casefold(),
            "requested product type",
            "wrong product type",
            "product type is undocumented",
        )

    customer_score = number(customer.get("credit_score"))
    if customer_score is not None:
        minimum = number(card.get("minimum_credit_score"))
        if "minimum_credit_score" in ambiguous or minimum is None:
            unknown.append("minimum credit-score requirement is undocumented")
        elif customer_score >= minimum:
            passed.append("no credit-score requirement" if minimum == 0 else "credit score meets documented minimum")
        else:
            failed.append("credit score is below documented minimum")

    for requirement_key, field, label in (
        ("max_foreign_transaction_fee_percent", "foreign_fee", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment", "minimum payment"),
    ):
        ceiling = number(requirements.get(requirement_key))
        if ceiling is None:
            continue
        actual = number(card.get(field))
        if field in ambiguous or actual is None:
            unknown.append(label + " is undocumented")
        elif actual <= ceiling:
            passed.append(label + " is within requested maximum")
        else:
            failed.append(label + " exceeds requested maximum")

    if requirements.get("requires_virtual_card_management") is True:
        assess(
            "virtual_cards", card.get("virtual_cards") is True,
            "virtual-card management available", "virtual-card management unavailable",
            "virtual-card management is undocumented",
        )

    membership = card.get("membership")
    if membership is not None:
        memberships = customer.get("memberships", [])
        if not isinstance(memberships, list):
            unknown.append("customer membership status is invalid")
        elif str(membership).casefold() in {str(item).casefold() for item in memberships}:
            passed.append("required membership held")
        else:
            failed.append("required membership is not held")

    status = "not_qualified" if failed else "needs_review" if unknown else "qualified"
    return {**card, "status": status, "evaluation": {"passed": passed, "failed": failed, "unknown": unknown}}


def message_for(matches: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ", ".join(card["name"] for card in matches)
    is_are = "is" if len(matches) == 1 else "are"
    paragraphs = [f"Based on the supplied product documents, {names} {is_are} a confirmed match for the published criteria you gave."]
    score = number(customer.get("credit_score"))

    for card in matches:
        facts: list[str] = []
        minimum = number(card.get("minimum_credit_score"))
        if minimum == 0:
            suffix = f", so your stated score of {shown(score)} does not exclude you from applying" if score is not None else ""
            facts.append("it has no credit-score requirement (published minimum is 0)" + suffix)
        elif minimum is not None:
            facts.append(f"its documented minimum credit score is {shown(minimum)}")

        fee_cap = number(requirements.get("max_foreign_transaction_fee_percent"))
        if fee_cap is not None:
            facts.append(f"its foreign transaction fee is {shown(card['foreign_fee'])}%, within your {shown(fee_cap)}% maximum")

        payment_cap = number(requirements.get("max_minimum_payment_percent"))
        if payment_cap is not None:
            facts.append(f"its minimum monthly payment is {shown(card['minimum_payment'])}% of the outstanding balance, within your {shown(payment_cap)}% maximum")

        if requirements.get("requires_virtual_card_management") is True:
            facts.append("virtual-card management is available and can help organize spending")
        paragraphs.append(f"{card['name']}: " + "; ".join(facts) + ".")

    if customer.get("income") is not None:
        paragraphs.append("No applicable documented income threshold was used in this comparison.")
    paragraphs.append("This comparison of published criteria does not guarantee approval.")
    return "\n\n".join(paragraphs)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
            raise ValueError("documents must be an array")
        customer, requirements = payload.get("customer", {}), payload.get("requirements", {})
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")

        evaluated = [evaluate(card, customer, requirements) for card in extract(payload["documents"])]
        qualified = [card for card in evaluated if card["status"] == "qualified"]
        if qualified:
            output = {
                "status": "confirmed_match",
                "message": message_for(qualified, customer, requirements),
                "qualified": qualified,
                "evaluated_cards": evaluated,
            }
        else:
            review_needed = any(card["status"] == "needs_review" for card in evaluated)
            output = {
                "status": "needs_review" if review_needed else "no_confirmed_match",
                "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.",
                "qualified": [],
                "evaluated_cards": evaluated,
            }
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"status": "invalid_input", "message": str(exc), "qualified": [], "evaluated_cards": []}
    print(json.dumps(output, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
