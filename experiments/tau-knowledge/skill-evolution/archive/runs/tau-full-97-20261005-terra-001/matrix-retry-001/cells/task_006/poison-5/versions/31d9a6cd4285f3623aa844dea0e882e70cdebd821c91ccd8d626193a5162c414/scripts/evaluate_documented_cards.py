#!/usr/bin/env python3
"""Extract conservative card facts from current-task documents and compare them.

Input is a JSON object containing documents, customer, and requirements as specified
in SKILL.md. Output includes extracted cards and the match_cards evaluation. Only
explicitly stated values are extracted; absence remains unknown.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any, Optional

from match_cards import evaluate_payload


def product_name(title: str) -> str:
    """Use the title prefix as a stable product grouping without document IDs."""
    return title.split(":", 1)[0].strip() or title.strip()


def first_match(text: str, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1)
    return None


def number(value: str) -> float:
    return float(value.replace("$", "").replace(",", ""))


def set_fact(card: dict[str, Any], key: str, value: Any, source: str) -> None:
    """Record a fact; conflicting explicit values become an ambiguity, not a choice."""
    sources = card.setdefault("field_sources", {}).setdefault(key, [])
    sources.append(source)
    if key not in card:
        card[key] = value
    elif card[key] != value:
        card.pop(key, None)
        card.setdefault("ambiguous_fields", []).append(key)


def extract_cards(documents: list[Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for document in documents:
        if not isinstance(document, dict):
            continue
        title = document.get("title")
        content = document.get("content")
        if not isinstance(title, str) or not isinstance(content, str) or not title.strip():
            continue
        name = product_name(title)
        card = grouped.setdefault(name, {"name": name, "field_sources": {}})
        source = str(document.get("document_id") or title)
        lower_title = title.casefold()
        if "business" in lower_title:
            set_fact(card, "product_type", "business", source)
        elif "card" in lower_title:
            set_fact(card, "product_type", "personal", source)

        score = first_match(content, [
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9][0-9,]*)",
            r"minimum\s+(?:personal\s+)?(?:fico\s+)?(?:credit\s+)?threshold\s+of\s*\$?([0-9][0-9,]*)",
            r"applications?\s+should\s+meet\s+at\s+least\s*\$?([0-9][0-9,]*)",
        ])
        if score is not None:
            set_fact(card, "minimum_credit_score", number(score), source)

        foreign_fee = first_match(content, [
            r"foreign\s+transaction\s+fee(?:\s+(?:on|for)[^:\n]*)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if foreign_fee is not None:
            set_fact(card, "foreign_transaction_fee_percent", number(foreign_fee), source)

        minimum_payment = first_match(content, [
            r"minimum\s+(?:monthly\s+)?payment\s+is\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
            r"minimum\s+(?:monthly\s+)?payment(?:\s+requirement)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%",
        ])
        if minimum_payment is not None:
            set_fact(card, "minimum_payment_percent", number(minimum_payment), source)

        virtual = first_match(content, [
            r"virtual[ -]card\s+management(?:\s+features)?\s+(?:are\s+)?available\s*:\s*(yes|no)",
            r"virtual[ -]card\s+management\s+availability\s*:\s*(yes|no)",
        ])
        if virtual is not None:
            set_fact(card, "virtual_card_management", virtual.casefold() == "yes", source)

        membership = first_match(content, [
            r"([A-Za-z0-9+ -]+)\s+(?:premium\s+)?subscription\s+required\s*:\s*yes",
        ])
        if membership is not None:
            memberships = card.setdefault("required_memberships", [])
            normalized = membership.strip()
            if normalized and normalized not in memberships:
                memberships.append(normalized)
                card.setdefault("field_sources", {}).setdefault("required_memberships", []).append(source)

    for card in grouped.values():
        ambiguous = card.get("ambiguous_fields", [])
        if ambiguous:
            card["ambiguous_fields"] = sorted(set(ambiguous))
    return list(grouped.values())


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise ValueError("documents must be an array of current-task product documents")
        cards = extract_cards(documents)
        comparison = evaluate_payload({
            "customer": payload.get("customer", {}),
            "requirements": payload.get("requirements", {}),
            "cards": cards,
        })
        output = {"extracted_cards": cards, **comparison}
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"error": "invalid_input", "message": str(exc)}
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
