#!/usr/bin/env python3
"""Deterministically compare card terms supplied as JSON documents.

Input: JSON object described in SKILL.md on stdin.
Output: one JSON object on stdout. No external calls or filesystem access occur.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def as_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", "").replace("%", ""))
    except (InvalidOperation, ValueError):
        return None


def show(value: Any) -> str:
    numeric = as_decimal(value)
    if numeric is None:
        return "unknown"
    text = format(numeric.normalize(), "f")
    return text if "." in text else text + ".0"


def capture(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        found = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if found:
            return found.group(1)
    return None


def product_name(title: str) -> str:
    return title.split(":", 1)[0].strip() or title.strip()


def add_fact(card: dict[str, Any], key: str, value: Any, source: str) -> None:
    """Add a sourced fact, marking the key ambiguous on contradictory values."""
    card["sources"].setdefault(key, []).append(source)
    if key in card["ambiguous"]:
        return
    if key not in card:
        card[key] = value
    elif card[key] != value:
        card.pop(key, None)
        card["ambiguous"].add(key)


def extract_cards(documents: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, text = document.get("title"), document.get("content")
        if not isinstance(title, str) or not title.strip() or not isinstance(text, str):
            continue
        name = product_name(title)
        card = grouped.setdefault(name, {"name": name, "sources": {}, "ambiguous": set()})
        source = str(document.get("document_id") or title)
        add_fact(card, "product_type", "business" if re.search(r"\bbusiness\b", title, re.I) else "personal", source)

        score = capture(text, (
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+(?:required|requirement))?(?:\s+to\s+apply)?\s*(?:is|:|of)?\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?fico\s+(?:threshold|score)\s*(?:is|:|of)?\s*\$?([0-9][0-9,]*)",
            r"(?:applications?\s+should\s+meet\s+at\s+least|score\s+of\s+at\s+least)\s*\$?([0-9][0-9,]*)",
        ))
        if score is not None and as_decimal(score) is not None:
            add_fact(card, "minimum_credit_score", as_decimal(score), source)

        fee = capture(text, (
            r"foreign\s+transaction\s+fee[^\n]{0,160}?(?:is|:|of)\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"foreign\s+transaction\s+fee[^\n]{0,160}?\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if fee is not None and as_decimal(fee) is not None:
            add_fact(card, "foreign_fee", as_decimal(fee), source)

        payment = capture(text, (
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*(?:is|:|of)?\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment[^\n]{0,160}?\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ))
        if payment is not None and as_decimal(payment) is not None:
            add_fact(card, "minimum_payment", as_decimal(payment), source)

        virtual = capture(text, (
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+available\s*:\s*(yes|no)",
        ))
        if virtual is not None:
            add_fact(card, "virtual_cards", virtual.casefold() == "yes", source)

        membership = capture(text, (r"([^\n:]+?)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes",))
        if membership is not None:
            add_fact(card, "membership", membership.strip(), source)

    output = []
    for card in grouped.values():
        card["ambiguous"] = sorted(card["ambiguous"])
        output.append(card)
    return output


def evaluate(card: dict[str, Any], customer: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    passed: list[str] = []
    failed: list[str] = []
    unknown: list[str] = []
    ambiguous = set(card["ambiguous"])

    def known(key: str) -> bool:
        return key not in ambiguous and key in card

    requested_type = requirements.get("product_type")
    if requested_type is not None:
        if not known("product_type"):
            unknown.append("product type is undocumented")
        elif str(card["product_type"]).casefold() == str(requested_type).casefold():
            passed.append("requested product type")
        else:
            failed.append("wrong product type")

    score = as_decimal(customer.get("credit_score"))
    if score is not None:
        if not known("minimum_credit_score"):
            unknown.append("minimum credit-score requirement is undocumented")
        elif score >= card["minimum_credit_score"]:
            passed.append("no credit-score requirement" if card["minimum_credit_score"] == 0 else "credit score meets documented minimum")
        else:
            failed.append("credit score is below documented minimum")

    for requirement_key, fact_key, label in (
        ("max_foreign_transaction_fee_percent", "foreign_fee", "foreign transaction fee"),
        ("max_minimum_payment_percent", "minimum_payment", "minimum monthly payment"),
    ):
        maximum = as_decimal(requirements.get(requirement_key))
        if maximum is None:
            continue
        if not known(fact_key):
            unknown.append(label + " is undocumented")
        elif card[fact_key] <= maximum:
            passed.append(label + " is within requested maximum")
        else:
            failed.append(label + " exceeds requested maximum")

    if requirements.get("requires_virtual_card_management") is True:
        if not known("virtual_cards"):
            unknown.append("virtual-card management is undocumented")
        elif card["virtual_cards"]:
            passed.append("virtual-card management available")
        else:
            failed.append("virtual-card management unavailable")

    if known("membership"):
        memberships = customer.get("memberships", [])
        if not isinstance(memberships, list):
            unknown.append("customer membership status is invalid")
        elif str(card["membership"]).casefold() in {str(x).casefold() for x in memberships}:
            passed.append("required membership held")
        else:
            failed.append("required membership is not held")

    status = "not_qualified" if failed else "needs_review" if unknown else "qualified"
    return {**card, "status": status, "evaluation": {"passed": passed, "failed": failed, "unknown": unknown}}


def message(matches: list[dict[str, Any]], customer: dict[str, Any], requirements: dict[str, Any]) -> str:
    names = ", ".join(card["name"] for card in matches)
    verb = "is" if len(matches) == 1 else "are"
    lines = [f"Based on the supplied product documents, {names} {verb} a documented match for your stated criteria."]
    score = as_decimal(customer.get("credit_score"))
    fee_max = as_decimal(requirements.get("max_foreign_transaction_fee_percent"))
    payment_max = as_decimal(requirements.get("max_minimum_payment_percent"))
    for card in matches:
        facts: list[str] = []
        minimum = card.get("minimum_credit_score")
        if minimum == 0:
            score_text = "it has no credit-score requirement (its published minimum is 0)"
            if score is not None:
                score_text += f", so your stated {show(score)} credit score does not exclude you from applying"
            facts.append(score_text)
        elif minimum is not None:
            facts.append(f"its documented credit-score minimum is {show(minimum)}")
        if fee_max is not None:
            facts.append(f"its foreign transaction fee is {show(card['foreign_fee'])}%, within your {show(fee_max)}% maximum")
        if payment_max is not None:
            facts.append(f"its minimum monthly payment is {show(card['minimum_payment'])}% of the outstanding balance, within your {show(payment_max)}% maximum")
        if requirements.get("requires_virtual_card_management") is True:
            facts.append("virtual-card management is available and can help organize spending")
        lines.append(card["name"] + ": " + "; ".join(facts) + ".")
    if customer.get("income") is not None:
        lines.append("No applicable documented income threshold was used in this comparison.")
    lines.append("This is a comparison of published criteria, not a guarantee of underwriting approval.")
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
        cards = extract_cards(payload["documents"])
        if not cards:
            raise ValueError("no usable product documents were supplied")
        evaluated = [evaluate(card, customer, requirements) for card in cards]
        qualified = [card for card in evaluated if card["status"] == "qualified"]
        if qualified:
            result = {"status": "confirmed_match", "message": message(qualified, customer, requirements), "qualified": qualified, "evaluated_cards": evaluated}
        else:
            status = "needs_review" if any(card["status"] == "needs_review" for card in evaluated) else "no_confirmed_match"
            result = {"status": status, "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.", "qualified": [], "evaluated_cards": evaluated}
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {"status": "invalid_input", "message": str(exc), "qualified": [], "evaluated_cards": []}
    print(json.dumps(result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
