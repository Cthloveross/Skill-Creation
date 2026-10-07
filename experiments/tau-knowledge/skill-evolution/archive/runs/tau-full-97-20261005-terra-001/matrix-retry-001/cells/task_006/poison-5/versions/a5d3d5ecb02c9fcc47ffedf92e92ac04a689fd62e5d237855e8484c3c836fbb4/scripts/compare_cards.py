#!/usr/bin/env python3
"""Evaluate supplied credit-card documents against normalized shopping criteria.

Input: one JSON object on stdin, as documented in SKILL.md.
Output: one JSON object on stdout.
This program only parses stdin and writes stdout; it makes no external calls.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def number(value: Any) -> Decimal | None:
    """Return a Decimal for common numeric forms, or None for absent/invalid input."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", "").replace("%", ""))
    except (InvalidOperation, ValueError):
        return None


def display(value: Any) -> str:
    parsed = number(value)
    if parsed is None:
        return "unknown"
    rendered = format(parsed.normalize(), "f")
    return rendered if "." in rendered else rendered + ".0"


def first_capture(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
    return None


def card_name(title: str) -> str:
    return title.split(":", 1)[0].strip()


def add_fact(card: dict[str, Any], field: str, value: Any, source: str) -> None:
    """Store agreeing facts; mark a field ambiguous if sources disagree."""
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
        title = document.get("title")
        content = document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
            continue

        name = card_name(title)
        card = cards.setdefault(name, {"name": name, "sources": {}, "ambiguous": set()})
        source = str(document.get("document_id") or title)
        add_fact(
            card,
            "product_type",
            "business" if re.search(r"\bbusiness\b", title, re.IGNORECASE) else "personal",
            source,
        )

        score = first_capture(content, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score\s*(?:required)?\s*(?:to\s+apply)?\s*(?:is|:|of)?\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?fico\s+(?:threshold|score)\s*(?:of|is|:)?\s*\$?([0-9][0-9,]*)",
            r"(?:applications?\s+should\s+meet\s+at\s+least|score\s+of\s+at\s+least)\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            parsed = number(score)
            if parsed is not None:
                add_fact(card, "minimum_credit_score", parsed, source)

        fee = first_capture(content, [
            r"foreign\s+transaction\s+fee[^\n]{0,120}?(?:is|:|of)\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"foreign\s+transaction\s+fee[^\n]{0,160}?\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if fee is not None:
            parsed = number(fee)
            if parsed is not None:
                add_fact(card, "foreign_fee", parsed, source)

        payment = first_capture(content, [
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*(?:is|:|of)?\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment[^\n]{0,120}?\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if payment is not None:
            parsed = number(payment)
            if parsed is not None:
                add_fact(card, "minimum_payment", parsed, source)

        virtual = first_capture(content, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+available\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            add_fact(card, "virtual_cards", virtual.casefold() == "yes", source)

        membership = first_capture(content, [
            r"([^\n:]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes"
        ])
        if membership is not None:
            add_fact(card, "membership", membership.strip(), source)

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

    def check(field: str, condition: bool, pass_note: str, fail_note: str, unknown_note: str) -> None:
        if field in ambiguous or card.get(field) is None:
            unknown.append(unknown_note)
        elif condition:
            passed.append(pass_note)
        else:
            failed.append(fail_note)

    requested_type = requirements.get("product_type")
    if requested_type is not None:
        check(
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
        maximum = number(requirements.get(requirement_key))
        if maximum is None:
            continue
        actual = number(card.get(field))
        if field in ambiguous or actual is None:
            unknown.append(label + " is undocumented")
        elif actual <= maximum:
            passed.append(label + " is within requested maximum")
        else:
            failed.append(label + " exceeds requested maximum")

    if requirements.get("requires_virtual_card_management") is True:
        check(
            "virtual_cards",
            card.get("virtual_cards") is True,
            "virtual-card management available",
            "virtual-card management unavailable",
            "virtual-card management is undocumented",
        )

    required_membership = card.get("membership")
    if required_membership is not None:
        memberships = customer.get("memberships", [])
        if not isinstance(memberships, list):
            unknown.append("customer membership status is invalid")
        elif str(required_membership).casefold() in {str(item).casefold() for item in memberships}:
            passed.append("required membership held")
        else:
            failed.append("required membership is not held")

    status = "not_qualified" if failed else "needs_review" if unknown else "qualified"
    return {**card, "status": status, "evaluation": {"passed": passed, "failed": failed, "unknown": unknown}}


def customer_message(matches: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ", ".join(item["name"] for item in matches)
    verb = "is" if len(matches) == 1 else "are"
    lines = [f"Based on the supplied product documents, {names} {verb} a confirmed match for the published criteria you gave."]
    score = number(customer.get("credit_score"))
    fee_cap = number(requirements.get("max_foreign_transaction_fee_percent"))
    payment_cap = number(requirements.get("max_minimum_payment_percent"))

    for card in matches:
        facts: list[str] = []
        minimum = number(card.get("minimum_credit_score"))
        if minimum == 0:
            text = "it has no credit-score requirement (the published minimum is 0)"
            if score is not None:
                text += f", so your stated {display(score)} credit score does not exclude you from applying"
            facts.append(text)
        elif minimum is not None:
            facts.append(f"its documented minimum credit score is {display(minimum)}")
        if fee_cap is not None:
            facts.append(f"its foreign transaction fee is {display(card['foreign_fee'])}%, within your {display(fee_cap)}% maximum")
        if payment_cap is not None:
            facts.append(f"its minimum monthly payment is {display(card['minimum_payment'])}% of the outstanding balance, within your {display(payment_cap)}% maximum")
        if requirements.get("requires_virtual_card_management") is True:
            facts.append("virtual-card management is available and can help organize spending")
        lines.append(f"{card['name']}: " + "; ".join(facts) + ".")

    if customer.get("income") is not None:
        lines.append("No applicable documented income threshold was used in this comparison.")
    lines.append("This published-criteria comparison does not guarantee underwriting approval.")
    return "\n\n".join(lines)


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
            output = {
                "status": "confirmed_match",
                "message": customer_message(qualified, customer, requirements),
                "qualified": qualified,
                "evaluated_cards": evaluated,
            }
        else:
            review = any(card["status"] == "needs_review" for card in evaluated)
            output = {
                "status": "needs_review" if review else "no_confirmed_match",
                "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.",
                "qualified": [],
                "evaluated_cards": evaluated,
            }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        output = {"status": "invalid_input", "message": str(exc), "qualified": [], "evaluated_cards": []}
    print(json.dumps(output, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
