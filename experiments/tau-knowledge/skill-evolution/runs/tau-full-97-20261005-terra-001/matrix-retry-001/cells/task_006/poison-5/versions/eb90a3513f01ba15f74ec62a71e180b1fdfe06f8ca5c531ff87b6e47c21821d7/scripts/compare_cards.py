#!/usr/bin/env python3
"""Compare supplied card-document evidence to normalized shopping criteria.

Input: one JSON object on stdin as documented in SKILL.md.
Output: one JSON object on stdout. No network, account, or banking operations occur.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_value(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def shown(value: Any) -> str:
    number = decimal_value(value)
    if number is None:
        return "unknown"
    text = format(number.normalize(), "f")
    return text if "." in text else text + ".0"


def capture(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)
    return None


def product_name(title: str) -> str:
    return title.split(":", 1)[0].strip()


def record_fact(card: dict[str, Any], field: str, value: Any, source: str) -> None:
    """Record agreeing evidence, and preserve disagreement as an ambiguity."""
    card.setdefault("sources", {}).setdefault(field, []).append(source)
    ambiguous = card.setdefault("ambiguous", set())
    if field in ambiguous:
        return
    if field not in card:
        card[field] = value
    elif card[field] != value:
        card.pop(field, None)
        ambiguous.add(field)


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
        card = products.setdefault(name, {"name": name, "sources": {}, "ambiguous": set()})
        source = str(document.get("document_id") or title)
        # Product classification comes from the document identity, not customer occupation.
        is_business = bool(re.search(r"\bbusiness\b", title, flags=re.IGNORECASE))
        record_fact(card, "product_type", "business" if is_business else "personal", source)

        score = capture(text, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score\s*(?:required)?\s*(?:to\s+apply)?\s*(?:is|:|of)?\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)",
            r"(?:applications?\s+should\s+meet\s+at\s+least|score\s+of\s+at\s+least)\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            record_fact(card, "minimum_credit_score", decimal_value(score), source)

        fee = capture(text, [
            r"foreign\s+transaction\s+fee[^\n:]{0,100}:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"foreign\s+transaction\s+fee[^\n0-9]{0,80}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if fee is not None:
            record_fact(card, "foreign_fee", decimal_value(fee), source)

        payment = capture(text, [
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*(?:is|:)?\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment[^\n0-9]{0,80}\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if payment is not None:
            record_fact(card, "minimum_payment", decimal_value(payment), source)

        virtual = capture(text, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+available\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            record_fact(card, "virtual_cards", virtual.casefold() == "yes", source)

        membership = capture(text, [
            r"([A-Za-z0-9+ -]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes"
        ])
        if membership is not None:
            record_fact(card, "membership", membership.strip(), source)

    result: list[dict[str, Any]] = []
    for card in products.values():
        card["ambiguous"] = sorted(card["ambiguous"])
        result.append(card)
    return result


def evaluate(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    ambiguous = set(card.get("ambiguous", []))

    def requirement(field: str, condition: bool, yes: str, no: str, missing: str) -> None:
        if field in ambiguous or card.get(field) is None:
            unknown.append(missing)
        elif condition:
            passed.append(yes)
        else:
            failed.append(no)

    desired_type = requirements.get("product_type")
    if desired_type is not None:
        requirement(
            "product_type",
            str(card.get("product_type", "")).casefold() == str(desired_type).casefold(),
            "requested product type",
            "wrong product type",
            "product type is undocumented",
        )

    score = decimal_value(customer.get("credit_score"))
    if score is not None:
        minimum = decimal_value(card.get("minimum_credit_score"))
        if "minimum_credit_score" in ambiguous or minimum is None:
            unknown.append("minimum credit-score requirement is undocumented")
        elif score >= minimum:
            passed.append("no credit-score requirement" if minimum == 0 else "credit score meets documented minimum")
        else:
            failed.append("credit score is below documented minimum")

    for input_key, fact, label in (
        ("max_foreign_transaction_fee_percent", "foreign_fee", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment", "minimum payment"),
    ):
        maximum = decimal_value(requirements.get(input_key))
        if maximum is None:
            continue
        actual = decimal_value(card.get(fact))
        if fact in ambiguous or actual is None:
            unknown.append(label + " is undocumented")
        elif actual <= maximum:
            passed.append(label + " is within requested maximum")
        else:
            failed.append(label + " exceeds requested maximum")

    if requirements.get("requires_virtual_card_management") is True:
        requirement(
            "virtual_cards", card.get("virtual_cards") is True,
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
    reply = [f"Based on the supplied product documents, {names} {verb} a confirmed match for the published criteria you gave."]
    score = decimal_value(customer.get("credit_score"))
    fee_limit = decimal_value(requirements.get("max_foreign_transaction_fee_percent"))
    payment_limit = decimal_value(requirements.get("max_minimum_payment_percent"))

    for card in matches:
        details: list[str] = []
        minimum = decimal_value(card.get("minimum_credit_score"))
        if minimum == 0:
            score_detail = "it has no credit-score requirement (the published minimum is 0)"
            if score is not None:
                score_detail += f", so your stated {shown(score)} score does not exclude you from applying"
            details.append(score_detail)
        elif minimum is not None:
            details.append(f"its documented minimum credit score is {shown(minimum)}")
        if fee_limit is not None:
            details.append(f"its foreign transaction fee is {shown(card['foreign_fee'])}%, within your {shown(fee_limit)}% maximum")
        if payment_limit is not None:
            details.append(f"its minimum monthly payment is {shown(card['minimum_payment'])}% of the outstanding balance, within your {shown(payment_limit)}% maximum")
        if requirements.get("requires_virtual_card_management") is True:
            details.append("virtual-card management is available and can help organize spending")
        reply.append(f"{card['name']}: " + "; ".join(details) + ".")

    if customer.get("income") is not None:
        reply.append("No applicable documented income threshold was used in this comparison.")
    reply.append("This published-criteria comparison does not guarantee underwriting approval.")
    return "\n\n".join(reply)


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
            result = {
                "status": "confirmed_match",
                "message": recommendation(qualified, customer, requirements),
                "qualified": qualified,
                "evaluated_cards": evaluated,
            }
        else:
            review_needed = any(card["status"] == "needs_review" for card in evaluated)
            result = {
                "status": "needs_review" if review_needed else "no_confirmed_match",
                "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.",
                "qualified": [],
                "evaluated_cards": evaluated,
            }
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {"status": "invalid_input", "message": str(exc), "qualified": [], "evaluated_cards": []}
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
