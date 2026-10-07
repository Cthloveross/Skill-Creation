#!/usr/bin/env python3
"""Compare supplied card documents against normalized customer requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. Uses only the
provided documents and performs no account or banking action.
"""
from __future__ import annotations

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def num(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", "").replace("%", ""))
    except (InvalidOperation, AttributeError):
        return None


def shown(value: Any) -> str:
    value = num(value)
    if value is None:
        return "unknown"
    text = format(value.normalize(), "f")
    return text if "." in text else text + ".0"


def find(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I | re.S)
        if match:
            return match.group(1)
    return None


def put(card: dict[str, Any], field: str, value: Any, source: str) -> None:
    card.setdefault("sources", {}).setdefault(field, []).append(source)
    if field in card.get("ambiguous", []):
        return
    if field not in card:
        card[field] = value
    elif card[field] != value:
        card.pop(field, None)
        card.setdefault("ambiguous", []).append(field)


def extract(documents: list[Any]) -> list[dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title, text = document.get("title"), document.get("content")
        if not isinstance(title, str) or not isinstance(text, str) or not title.strip():
            continue
        name = title.split(":", 1)[0].strip()
        card = cards.setdefault(name, {"name": name, "sources": {}})
        source = str(document.get("document_id") or title)
        if "business" in title.casefold():
            put(card, "product_type", "business", source)
        elif "card" in title.casefold():
            put(card, "product_type", "personal", source)

        score = find(text, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?(?:credit\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)",
            r"applications?\s+should\s+meet\s+at\s+least\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            put(card, "minimum_credit_score", num(score), source)
        foreign = find(text, [r"foreign\s+transaction\s+fee(?:\s+(?:on|for)[^:\n]*)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%"])
        if foreign is not None:
            put(card, "foreign_fee", num(foreign), source)
        payment = find(text, [
            r"minimum\s+(?:monthly\s+)?payment\s+is\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if payment is not None:
            put(card, "minimum_payment", num(payment), source)
        virtual = find(text, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            put(card, "virtual_cards", virtual.casefold() == "yes", source)
        membership = find(text, [r"([A-Za-z0-9+ -]+)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes"])
        if membership:
            put(card, "membership", membership.strip(), source)
    return list(cards.values())


def evaluate(card: dict[str, Any], customer: dict[str, Any], req: dict[str, Any]) -> dict[str, Any]:
    passed, failed, unknown = [], [], []
    ambiguous = set(card.get("ambiguous", []))

    def check(field: str, condition: bool, good: str, bad: str, missing: str) -> None:
        if field in ambiguous or card.get(field) is None:
            unknown.append(missing)
        elif condition:
            passed.append(good)
        else:
            failed.append(bad)

    wanted_type = req.get("product_type")
    if wanted_type is not None:
        check("product_type", str(card.get("product_type", "")).casefold() == str(wanted_type).casefold(), "requested product type", "wrong product type", "product type is undocumented")
    score = num(customer.get("credit_score"))
    if score is not None:
        threshold = num(card.get("minimum_credit_score"))
        if "minimum_credit_score" in ambiguous or threshold is None:
            unknown.append("minimum credit-score requirement is undocumented")
        elif score < threshold:
            failed.append("credit score is below the documented minimum")
        else:
            passed.append("no credit-score requirement" if threshold == 0 else "credit score meets documented minimum")
    for req_field, card_field, label in (("max_foreign_transaction_fee_percent", "foreign_fee", "foreign transaction fee"), ("max_minimum_payment_percent", "minimum_payment", "minimum payment")):
        ceiling, actual = num(req.get(req_field)), num(card.get(card_field))
        if ceiling is not None:
            if card_field in ambiguous or actual is None:
                unknown.append(label + " is undocumented")
            elif actual > ceiling:
                failed.append(label + " exceeds requested maximum")
            else:
                passed.append(label + " is within requested maximum")
    if req.get("requires_virtual_card_management") is True:
        check("virtual_cards", card.get("virtual_cards") is True, "virtual-card management available", "virtual-card management unavailable", "virtual-card management is undocumented")
    required = card.get("membership")
    if required:
        held = customer.get("memberships", [])
        if not isinstance(held, list):
            unknown.append("customer membership status is invalid")
        elif str(required).casefold() not in {str(x).casefold() for x in held}:
            failed.append("required membership is not held")
        else:
            passed.append("required membership held")
    status = "not_qualified" if failed else "needs_review" if unknown else "qualified"
    return {**card, "status": status, "evaluation": {"passed": passed, "failed": failed, "unknown": unknown}}


def message(matches: list[dict[str, Any]], customer: dict[str, Any], req: dict[str, Any]) -> str:
    paragraphs = ["Based on the supplied product documents, " + ", ".join(c["name"] for c in matches) + (" is" if len(matches) == 1 else " are") + " a confirmed match for the published criteria you gave."]
    score = num(customer.get("credit_score"))
    for card in matches:
        terms = []
        threshold = num(card.get("minimum_credit_score"))
        if threshold == 0:
            suffix = "" if score is None else f", so your stated score of {shown(score)} does not exclude you from applying"
            terms.append("it has no credit-score requirement (published minimum: 0)" + suffix)
        elif threshold is not None:
            terms.append("its documented minimum credit score is " + shown(threshold))
        if req.get("max_foreign_transaction_fee_percent") is not None:
            terms.append(f"its foreign transaction fee is {shown(card['foreign_fee'])}%, within your {shown(req['max_foreign_transaction_fee_percent'])}% maximum")
        if req.get("max_minimum_payment_percent") is not None:
            terms.append(f"its minimum monthly payment is {shown(card['minimum_payment'])}% of the outstanding balance, within your {shown(req['max_minimum_payment_percent'])}% maximum")
        if req.get("requires_virtual_card_management") is True:
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
        customer, req = payload.get("customer", {}), payload.get("requirements", {})
        if not isinstance(customer, dict) or not isinstance(req, dict):
            raise ValueError("customer and requirements must be objects")
        cards = [evaluate(c, customer, req) for c in extract(payload["documents"])]
        qualified = [c for c in cards if c["status"] == "qualified"]
        if qualified:
            output = {"status": "confirmed_match", "message": message(qualified, customer, req), "qualified": qualified, "evaluated_cards": cards}
        else:
            output = {"status": "needs_review" if any(c["status"] == "needs_review" for c in cards) else "no_confirmed_match", "message": "No confirmed match was found after evaluating the supplied product documents. This is not an approval decision.", "qualified": [], "evaluated_cards": cards}
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"status": "invalid_input", "message": str(exc)}
    print(json.dumps(output, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
