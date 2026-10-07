#!/usr/bin/env python3
"""Select and phrase the highest flat everyday cash-back card from product terms.

Input (stdin):
{"documents": [{"document_id": str, "title": str, "content": str}, ...]}

Output (stdout): either
{"status": "ok", "recommendation": {...}, "customer_message": str}
or
{"status": "needs_review", "reason": str}.

Only Python's standard library is used. The script intentionally recognizes only
rates explicitly stated as applying to all purchases or all eligible purchases;
category-specific rewards are not everyday flat-rate candidates.
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
        r"(?P<rate>\d+(?:\.\d+)?)\s*%\s+cash\s+back\s+on\s+all\s+(?:eligible\s+)?purchases",
        re.IGNORECASE,
    ),
    re.compile(
        r"cash\s+back\s+on\s+all\s+(?:eligible\s+)?purchases\s*:\s*\$?(?P<rate>\d+(?:\.\d+)?)\s*%",
        re.IGNORECASE,
    ),
)
FEE_PATTERNS = (
    re.compile(r"annual\s+fee\s*:\s*\$?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"annual\s+fee\s+of\s+\$?\s*(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"\$\s*(\d+(?:\.\d+)?)\s+annual\s+fee", re.IGNORECASE),
)
SCORE_PATTERN = re.compile(
    r"minimum\s+credit\s+score(?:\s+required)?\s*:\s*\$?\s*(\d+)", re.IGNORECASE
)


def decimal_text(value: str) -> Optional[str]:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0:
        return None
    return str(number)


def card_name(title: str) -> str:
    """Extract the stable card-name prefix from conventional product titles."""
    name = title.split(":", 1)[0].strip()
    return name if name and "card" in name.lower() else ""


def rates_in(content: str) -> Set[str]:
    rates: Set[str] = set()
    for pattern in RATE_PATTERNS:
        for match in pattern.finditer(content):
            rate = decimal_text(match.group("rate"))
            if rate is not None:
                rates.add(rate)
    return rates


def fees_in(content: str) -> Set[str]:
    fees: Set[str] = set()
    for pattern in FEE_PATTERNS:
        for match in pattern.finditer(content):
            fee = decimal_text(match.group(1))
            if fee is not None:
                fees.add(fee)
    return fees


def validate_documents(payload: Any) -> List[Tuple[str, str, str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ValueError("input must be an object containing a documents array")
    if not payload["documents"]:
        raise ValueError("documents must contain at least one product document")

    validated: List[Tuple[str, str, str]] = []
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
        validated.append((doc_id.strip(), title.strip(), content))
    return validated


def collect_candidates(documents: List[Tuple[str, str, str]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    grouped: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for doc_id, title, content in documents:
        name = card_name(title)
        if name:
            grouped[name].append((doc_id, content))

    candidates: List[Dict[str, Any]] = []
    conflicts: List[str] = []
    for name, records in grouped.items():
        rates: Set[str] = set()
        rate_evidence: List[str] = []
        fees: Set[str] = set()
        constraints: List[str] = []
        invitation_only = False

        for doc_id, content in records:
            found_rates = rates_in(content)
            if found_rates:
                rates.update(found_rates)
                rate_evidence.append(doc_id)
            fees.update(fees_in(content))
            for score in SCORE_PATTERN.findall(content):
                text = f"Minimum credit score required: {score}"
                if text not in constraints:
                    constraints.append(text)
            if re.search(r"invitation[\s-]*only", content, re.IGNORECASE):
                invitation_only = True

        if not rates:
            continue
        if len(rates) != 1:
            conflicts.append(name)
            continue

        # A varying or promotional fee is not safe to state as a single current fee.
        annual_fee = next(iter(fees)) if len(fees) == 1 else None
        candidates.append(
            {
                "name": name,
                "personal": "business" not in name.lower(),
                "ordinary_application_available": not invitation_only,
                "cash_back_rate_percent": next(iter(rates)),
                "annual_fee": annual_fee,
                "eligibility_constraints": constraints,
                "evidence": sorted(set(rate_evidence)),
            }
        )
    return candidates, sorted(conflicts)


def money(value: Decimal) -> str:
    return f"${value:.2f}"


def choose(payload: Any) -> Dict[str, Any]:
    documents = validate_documents(payload)
    candidates, conflicts = collect_candidates(documents)
    if conflicts:
        return {
            "status": "needs_review",
            "reason": "Conflicting flat all-purchases cash-back rates were documented for: "
            + ", ".join(conflicts)
            + ".",
        }

    qualifying = [
        card for card in candidates
        if card["personal"] and card["ordinary_application_available"]
    ]
    if not qualifying:
        return {
            "status": "needs_review",
            "reason": "No ordinarily available personal card has an explicit documented flat cash-back rate on all purchases or all eligible purchases.",
        }

    highest = max(Decimal(card["cash_back_rate_percent"]) for card in qualifying)
    winners = [
        card for card in qualifying
        if Decimal(card["cash_back_rate_percent"]) == highest
    ]
    if len(winners) != 1:
        return {
            "status": "needs_review",
            "reason": "The highest documented qualifying flat cash-back rate is tied and no supplied tie-breaker resolves it.",
            "tied_card_names": [card["name"] for card in winners],
            "rate_percent": str(highest),
        }

    winner = winners[0]
    sentences = [
        f"I recommend the {winner['name']}.",
        f"It earns {winner['cash_back_rate_percent']}% cash back on all eligible purchases—the highest documented flat rate for everyday spending.",
    ]
    if winner["annual_fee"] is not None:
        sentences.append(
            f"Its documented annual fee is {money(Decimal(winner['annual_fee']))}."
        )
    if winner["eligibility_constraints"]:
        sentences.append(
            "Documented access requirement: "
            + "; ".join(winner["eligibility_constraints"])
            + "."
        )

    recommendation = {
        "name": winner["name"],
        "cash_back_rate_percent": winner["cash_back_rate_percent"],
        "annual_fee": winner["annual_fee"],
        "eligibility_constraints": winner["eligibility_constraints"],
        "evidence": winner["evidence"],
    }
    return {
        "status": "ok",
        "recommendation": recommendation,
        "customer_message": " ".join(sentences),
        "selection_basis": "Unique highest documented flat cash-back rate on all eligible personal everyday purchases.",
    }


def main() -> None:
    try:
        result = choose(json.load(sys.stdin))
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"status": "needs_review", "reason": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
