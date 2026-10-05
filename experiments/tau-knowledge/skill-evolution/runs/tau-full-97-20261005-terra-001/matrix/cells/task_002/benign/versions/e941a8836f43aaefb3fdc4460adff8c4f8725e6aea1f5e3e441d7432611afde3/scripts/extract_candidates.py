#!/usr/bin/env python3
"""Extract flat personal-card cash-back candidates from supplied product documents.

Input:  {"documents": [{"document_id": str, "title": str, "content": str}, ...]}
Output: {"status": "ok", "cards": [...]} or a needs_review object.
Only the Python standard library is used.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

RATE_PATTERNS = (
    re.compile(
        r"(?P<rate>\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+eligible\s+purchases",
        re.IGNORECASE,
    ),
    re.compile(
        r"cash\s+back\s+on\s+all\s+(?:eligible\s+)?purchases\s*:\s*\$?(?P<rate>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
)
FEE_PATTERNS = (
    re.compile(r"annual\s+fee\s*:\s*\$?(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\$?(\d+(?:\.\d+)?)\s+annual\s+fee", re.IGNORECASE),
)
SCORE_PATTERN = re.compile(
    r"minimum\s+credit\s+score(?:\s+required)?\s*:\s*\$?(\d+)", re.IGNORECASE
)


def _card_name(title: str) -> str:
    """Use the document-title prefix convention while rejecting unusable titles."""
    name = title.split(":", 1)[0].strip()
    if not name or "card" not in name.lower():
        return ""
    return name


def _decimal_text(value: str) -> Optional[str]:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0:
        return None
    return str(number)


def _first_fee(content: str) -> Optional[str]:
    for pattern in FEE_PATTERNS:
        match = pattern.search(content)
        if match:
            return _decimal_text(match.group(1))
    return None


def _rate_values(content: str) -> Set[str]:
    values: Set[str] = set()
    for pattern in RATE_PATTERNS:
        for match in pattern.finditer(content):
            value = _decimal_text(match.group("rate"))
            if value is not None:
                values.add(value)
    return values


def extract(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ValueError("input must be an object with a documents array")

    grouped: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for index, document in enumerate(payload["documents"]):
        if not isinstance(document, dict):
            raise ValueError(f"documents[{index}] must be an object")
        doc_id = document.get("document_id")
        title = document.get("title")
        content = document.get("content")
        if not all(isinstance(value, str) and value.strip() for value in (doc_id, title, content)):
            raise ValueError(
                f"documents[{index}] requires nonempty document_id, title, and content strings"
            )
        name = _card_name(title)
        if name:
            grouped[name].append((doc_id.strip(), content))

    cards: List[Dict[str, Any]] = []
    conflicts: List[str] = []
    for name, documents in grouped.items():
        rates: Set[str] = set()
        rate_sources: List[str] = []
        fees: Set[str] = set()
        constraints: List[str] = []
        invitation_only = False
        for doc_id, content in documents:
            found_rates = _rate_values(content)
            if found_rates:
                rates.update(found_rates)
                rate_sources.append(doc_id)
            fee = _first_fee(content)
            if fee is not None:
                fees.add(fee)
            for score in SCORE_PATTERN.findall(content):
                requirement = f"Minimum credit score required: {score}"
                if requirement not in constraints:
                    constraints.append(requirement)
            if re.search(r"invitation[\s-]*only", content, re.IGNORECASE):
                invitation_only = True

        # No explicit all-purchases rate was found for this card.
        if not rates:
            continue
        if len(rates) != 1:
            conflicts.append(name)
            continue

        # Conflicting fee documents should not cause an unsupported fee disclosure.
        fee_value = next(iter(fees)) if len(fees) == 1 else None
        cards.append(
            {
                "name": name,
                "personal": "business" not in name.lower(),
                "cash_back_rate_percent": next(iter(rates)),
                "applies_to_all_eligible_purchases": True,
                "ordinary_application_available": not invitation_only,
                "annual_fee": fee_value,
                "eligibility_constraints": constraints,
                "conditions": [],
                "evidence": sorted(set(rate_sources)),
            }
        )

    if conflicts:
        return {
            "status": "needs_review",
            "reason": "Conflicting documented flat cash-back rates were found for: " + ", ".join(sorted(conflicts)) + ".",
            "conflicting_cards": sorted(conflicts),
        }
    if not cards:
        return {
            "status": "needs_review",
            "reason": "No personal card with an explicit flat cash-back rate on all eligible purchases could be extracted from the supplied documents.",
        }
    return {"status": "ok", "cards": sorted(cards, key=lambda card: card["name"].lower())}


def main() -> None:
    try:
        result = extract(json.load(sys.stdin))
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"status": "needs_review", "reason": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
