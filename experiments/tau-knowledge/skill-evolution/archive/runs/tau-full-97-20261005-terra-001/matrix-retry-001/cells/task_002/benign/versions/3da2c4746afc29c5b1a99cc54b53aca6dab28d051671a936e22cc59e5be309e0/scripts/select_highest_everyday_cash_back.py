#!/usr/bin/env python3
"""Select the highest explicitly documented broad-purchase cash-back card.

Input JSON:
  {"documents": [{"title": str, "content": str}, ...]}

Output JSON status values:
  ok, no_qualifying_candidate, tie_requires_resolution, invalid_input.

The selector ranks only earn rates that explicitly apply broadly to purchases.
It excludes category bonuses, introductory offers, redemption conversion rates,
fees, APRs, and transaction examples.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set, Tuple

RATE = r"(?P<rate>\d+(?:\.\d+)?)"
TITLE_PREFIX = re.compile(r"^\s*([^:\n]+?)\s*:")

# Each expression requires a percentage rate plus wording that establishes a
# broad purchase scope. Expressions are deliberately not category-rate patterns.
BROAD_RATE_PATTERNS = (
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?"
        + RATE
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?eligible\s+"
        r"(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?"
        + RATE
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+all\s+(?:purchases|spend|categories)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcash\s*back\s+on\s+all\s+(?:eligible\s+)?(?:purchases|spend|categories)"
        r"\s*:\s*"
        + RATE
        + r"\s*%\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?"
        + RATE
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?everyday\s+"
        r"(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
)


def error(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "error": message}


def product_name(title: str) -> Optional[str]:
    """Return the product-name portion of a conventional 'Product: topic' title."""
    match = TITLE_PREFIX.match(title)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def documented_broad_rates(content: str) -> Set[Decimal]:
    """Extract nonnegative finite rate values tied to an explicit broad scope."""
    rates: Set[Decimal] = set()
    for pattern in BROAD_RATE_PATTERNS:
        for match in pattern.finditer(content):
            try:
                rate = Decimal(match.group("rate"))
            except (InvalidOperation, TypeError):
                continue
            if rate.is_finite() and rate >= 0:
                rates.add(rate)
    return rates


def display_rate(rate: Decimal) -> str:
    """Use a stable percentage spelling while retaining an explicit decimal place."""
    text = format(rate.normalize(), "f")
    if "." not in text:
        return text + ".0"
    text = text.rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def parse_candidates(payload: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None, error("top-level input must be an object")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return None, error("documents must be an array")

    rates_by_product: Dict[str, Set[Decimal]] = {}
    source_titles: Dict[str, List[str]] = {}

    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            return None, error(f"documents[{index}] must be an object")
        title = document.get("title")
        content = document.get("content")
        if not isinstance(title, str) or not title.strip():
            return None, error(f"documents[{index}].title must be a nonempty string")
        if not isinstance(content, str):
            return None, error(f"documents[{index}].content must be a string")

        name = product_name(title)
        if name is None:
            continue
        rates = documented_broad_rates(content)
        if rates:
            rates_by_product.setdefault(name, set()).update(rates)
            source_titles.setdefault(name, []).append(title)

    candidates: List[Dict[str, Any]] = []
    for name in sorted(rates_by_product):
        rates = rates_by_product[name]
        if len(rates) != 1:
            return None, error(
                "conflicting broad-purchase cash-back rates documented for " + name
            )
        rate = next(iter(rates))
        candidates.append(
            {
                "product_name": name,
                "earn_rate_percent": float(rate),
                "earn_scope": "all_eligible_purchases",
                "source_titles": source_titles[name],
            }
        )
    return candidates, None


def select(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "status": "no_qualifying_candidate",
            "reason": "No explicit broad-purchase cash-back rate was found.",
            "qualifying_candidates": [],
        }

    highest = max(Decimal(str(item["earn_rate_percent"])) for item in candidates)
    leaders = [
        item for item in candidates
        if Decimal(str(item["earn_rate_percent"])) == highest
    ]
    if len(leaders) != 1:
        return {
            "status": "tie_requires_resolution",
            "highest_earn_rate_percent": float(highest),
            "tied_candidates": leaders,
            "qualifying_candidates": candidates,
        }

    winner = leaders[0]
    percentage = display_rate(highest)
    response = (
        f"I recommend the {winner['product_name']}. It earns {percentage}% cash back "
        "on all eligible purchases, making it the highest documented rate for everyday spending."
    )
    return {
        "status": "ok",
        "recommendation": winner,
        "qualifying_candidates": candidates,
        "customer_response": response,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(error(f"invalid JSON: {exc.msg}"), sort_keys=True))
        return

    candidates, parse_error = parse_candidates(payload)
    result = parse_error if parse_error is not None else select(candidates or [])
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
