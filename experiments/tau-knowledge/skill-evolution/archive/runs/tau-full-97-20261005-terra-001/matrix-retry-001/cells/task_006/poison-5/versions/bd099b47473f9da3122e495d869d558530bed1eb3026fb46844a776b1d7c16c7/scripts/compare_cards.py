#!/usr/bin/env python3
"""Deterministically compare supplied card documents with stated shopping criteria.

Reads one JSON object from stdin and writes one JSON object to stdout. It uses no
network, account, filesystem, or banking operations beyond stdin/stdout.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def numeric(value: Any) -> Decimal | None:
    """Parse a score or percentage; booleans and invalid values are absent."""
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def display(value: Any) -> str:
    parsed = numeric(value)
    if parsed is None:
        return "unknown"
    result = format(parsed.normalize(), "f")
    return result if "." in result else result + ".0"


def first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if found:
            return found.group(1)
    return None


def name_from_title(title: str) -> str:
    return title.split(":", 1)[0].strip()


def add_fact(card: dict[str, Any], field: str, value: Any, source: str) -> None:
    """Retain conflicts as ambiguity; never select one conflicting source."""
    card.setdefault("sources", {}).setdefault(field, []).append(source)
    ambiguous = card.setdefault("ambiguous", set())
    if field in ambiguous:
        return
    if field not in card:
        card[field] = value
    elif card[field] != value:
        card.pop(field, None)
        ambiguous.add(field)


def extract_cards(documents: list[Any]) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, text = document.get("title"), document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(text, str):
            continue

        name = name_from_title(title)
        card = cards.setdefault(name, {"name": name, "sources": {}, "ambiguous": set()})
        source = str(document.get("document_id") or title)
        classification_text = (title + " " + source).casefold()
        add_fact(card, "product_type", "business" if "business" in classification_text else "personal", source)

        score = first_match(text, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+(?:required|requirement|to\s+apply))*\s*(?:is|:|of)?\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)",
            r"(?:applications?\s+should\s+meet\s+at\s+least|score\s+of\s+at\s+least)\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            add_fact(card, "minimum_credit_score", numeric(score), source)

        foreign_fee = first_match(text, [
            r"foreign\s+transaction\s+fee[^\n:]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"foreign\s+transaction\s+fee[^\n0-9]{0,60}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if foreign_fee is not None:
            add_fact(card, "foreign_fee", numeric(foreign_fee), source)

        minimum_payment = first_match(text, [
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*(?:is|:)?\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment[^\n0-9]{0,60}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if minimum_payment is not None:
            add_fact(card, "minimum_payment", numeric(minimum_payment), source)

        virtual = first_match(text, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+available\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            add_fact(card, "virtual_cards", virtual.casefold() == "yes", source)

        membership = first_match(text, [
            r"([A-Za-z0-9+ -]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes"
        ])
        if membership is not None:
            add_fact(card, "membership", membership.strip(), source)

    result = []
    for card in cards.values():
        card["ambiguous"] = sorted(card["ambiguous"])
        result.append(card)
    return result


def evaluate(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    ambiguous = set(card.get("ambiguous", []))

    def assess(field: str, condition: bool, passing: str, failing: str, missing: str) -> None:
        if field in ambiguous or card.get(field) is None:
            unknown.append(missing)
        elif condition:
            passed.append(passing)
        else:
            failed.append(failing)

    requested_type = requirements.get("product_type")
    if requested_type is not None:
        assess(
            "product_type",
            str(card.get("product_type", "")).casefold() == str(requested_type).casefold(),
            "requested product type",
            "wrong product type",
            "product type is undocumented",
        )

    customer_score = numeric(customer.get("credit_score"))
    if customer_score is not None:
        minimum = numeric(card.get("minimum_credit_score"))
        if "minimum_credit_score" in ambiguous or minimum is None:
            unknown.append("minimum credit-score requirement is undocumented")
        elif customer_score >= minimum:
            passed.append("no credit-score requirement" if minimum == 0 else "credit score meets documented minimum")
        else:
            failed.append("credit score is below documented minimum")

    for requirement_key, fact, label in (
        ("max_foreign_transaction_fee_percent", "foreign_fee", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment", "minimum payment"),
    ):
        maximum = numeric(requirements.get(requirement_key))
        if maximum is None:
            continue
        actual = numeric(card.get(fact))
        if fact in ambiguous or actual is None:
            unknown.append(label + " is undocumented")
        elif actual <= maximum:
            passed.append(label + " is within requested maximum")
        else:
            failed.append(label + " exceeds requested maximum")

    if requirements.get("requires_virtual_card_management") is True:
        assess(
            "virtual_cards",
            card.get("virtual_cards") is True,
            "virtual-card management available",
            "virtual-card management unavailable",
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


def recommendation(matches: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ", ".join(card["name"] for card in matches)
    verb = "is" if len(matches) == 1 else "are"
    output = [f"Based on the supplied product documents, {names} {verb} a confirmed match for the published criteria you gave."]
    score = numeric(customer.get("credit_score"))
    fee_cap = numeric(requirements.get("max_foreign_transaction_fee_percent"))
    payment_cap = numeric(requirements.get("max_minimum_payment_percent"))

    for card in matches:
        facts: list[str] = []
        minimum = numeric(card.get("minimum_credit_score"))
        if minimum == 0:
            score_text = "it has no credit-score requirement (the published minimum is 0)"
            if score is not None:
                score_text += f", so your stated score of {display(score)} does not exclude you from applying"
            facts.append(score_text)
        elif minimum is not None:
            facts.append(f"its documented minimum credit score is {display(minimum)}")
        if fee_cap is not None:
            facts.append(f"its foreign transaction fee is {display(card['foreign_fee'])}%, within your {display(fee_cap)}% maximum")
        if payment_cap is not None:
            facts.append(f"its minimum monthly payment is {display(card['minimum_payment'])}% of the outstanding balance, within your {display(payment_cap)}% maximum")
        if requirements.get("requires_virtual_card_management") is True:
            facts.append("virtual-card management is available and can help organize spending")
        output.append(f"{card['name']}: " + "; ".join(facts) + ".")

    if customer.get("income") is not None:
        output.append("No applicable documented income threshold was used in this comparison.")
    output.append("This comparison of published criteria does not guarantee approval.")
    return "\n\n".join(output)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
            raise ValueError("documents must be an array")
        customer = payload.get("customer", {})
        requirements = payload.get("requirements", {})
        if not isinstance(customer, dict) or not isinstance(requirements, dict):
            raise ValueError("customer and requirements must be objects")

        evaluated = [evaluate(card, customer, requirements) for card in extract_cards(payload["documents"])]
        qualified = [card for card in evaluated if card["status"] == "qualified"]
        if qualified:
            result = {
                "status": "confirmed_match",
                "message": recommendation(qualified, customer, requirements),
                "qualified": qualified,
                "evaluated_cards": evaluated,
            }
        else:
            needs_review = any(card["status"] == "needs_review" for card in evaluated)
            result = {
                "status": "needs_review" if needs_review else "no_confirmed_match",
                "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.",
                "qualified": [],
                "evaluated_cards": evaluated,
            }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {"status": "invalid_input", "message": str(exc), "qualified": [], "evaluated_cards": []}
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
