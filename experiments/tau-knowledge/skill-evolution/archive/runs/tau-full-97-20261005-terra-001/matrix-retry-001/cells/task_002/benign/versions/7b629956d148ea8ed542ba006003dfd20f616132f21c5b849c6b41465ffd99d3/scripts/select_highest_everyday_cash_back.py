#!/usr/bin/env python3
"""Select the highest explicitly documented broad-purchase cash-back card.

Input JSON:
  {"documents": [{"title": str, "content": str}, ...]}

Output statuses:
  - ok: one highest broad-purchase card plus a ready-to-send response
  - no_qualifying_candidate: no explicit broad-purchase cash-back rate found
  - tie_requires_resolution: multiple products share the highest rate
  - invalid_input: input does not conform to the documented schema

Only explicitly broad cash-back rates are ranked. Category-specific rates,
bonuses, redemption conversions, and fee disclosures are excluded.
"""

import json
import math
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

NUMBER = r"(\d+(?:\.\d+)?)"
TITLE_NAME = re.compile(r"^\s*([^:\n]+?)\s*:")

# Each pattern requires both an earning rate and an explicit broad purchase scope.
BROAD_RATE_PATTERNS = (
    # "You earn 2.5% cash back on all eligible purchases."
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + NUMBER
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?eligible\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
    # "You earn 2.5% cash back on all purchases."
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + NUMBER
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+all\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
    # "Cash back on all purchases: 2.5%"
    re.compile(
        r"\bcash\s*back\s+on\s+all\s+(?:eligible\s+)?(?:purchases|spend)\s*:\s*"
        + NUMBER + r"\s*%",
        re.IGNORECASE,
    ),
    # "Earn 2.5% on everyday purchases."
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + NUMBER
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?everyday\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
)


def invalid(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "error": message}


def card_name(title: str) -> Optional[str]:
    """Extract a product-name prefix from a standard 'Product: topic' title."""
    match = TITLE_NAME.match(title)
    if not match:
        return None
    name = match.group(1).strip()
    return name or None


def broad_rates(content: str) -> Set[float]:
    """Return finite nonnegative rates that have explicit broad-purchase scope."""
    found: Set[float] = set()
    for pattern in BROAD_RATE_PATTERNS:
        for match in pattern.finditer(content):
            rate = float(match.group(1))
            if math.isfinite(rate) and rate >= 0:
                found.add(rate)
    return found


def format_percent(rate: float) -> str:
    text = f"{rate:.10f}".rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def parse_documents(payload: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None, invalid("top-level input must be an object")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return None, invalid("documents must be an array")

    by_product: Dict[str, Set[float]] = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            return None, invalid(f"documents[{index}] must be an object")
        title = document.get("title")
        content = document.get("content")
        if not isinstance(title, str) or not title.strip():
            return None, invalid(f"documents[{index}].title must be a nonempty string")
        if not isinstance(content, str):
            return None, invalid(f"documents[{index}].content must be a string")

        product = card_name(title)
        if product is None:
            continue
        rates = broad_rates(content)
        if rates:
            by_product.setdefault(product, set()).update(rates)

    candidates: List[Dict[str, Any]] = []
    for product in sorted(by_product):
        rates = by_product[product]
        if len(rates) != 1:
            return None, invalid(
                f"conflicting broad-purchase cash-back rates documented for {product}"
            )
        candidates.append({
            "product_name": product,
            "earn_rate_percent": next(iter(rates)),
            "earn_scope": "all_eligible_purchases",
        })
    return candidates, None


def select(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "status": "no_qualifying_candidate",
            "reason": "No explicit cash-back rate for broad eligible purchases was found.",
            "qualifying_candidates": [],
        }

    highest = max(item["earn_rate_percent"] for item in candidates)
    leaders = [item for item in candidates if item["earn_rate_percent"] == highest]
    if len(leaders) != 1:
        return {
            "status": "tie_requires_resolution",
            "highest_earn_rate_percent": highest,
            "tied_candidates": leaders,
            "qualifying_candidates": candidates,
        }

    winner = leaders[0]
    response = (
        f"I recommend the {winner['product_name']}. It earns "
        f"{format_percent(winner['earn_rate_percent'])}% cash back on all eligible purchases, "
        "the highest documented rate for everyday spending."
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
        print(json.dumps(invalid(f"invalid JSON: {exc.msg}"), sort_keys=True))
        return

    candidates, error = parse_documents(payload)
    result = error if error is not None else select(candidates or [])
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
