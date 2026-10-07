#!/usr/bin/env python3
"""Select the highest explicitly documented broad-purchase cash-back card.

Input JSON:
  {"documents": [{"title": str, "content": str}, ...]}

Output JSON has one of these statuses:
  - ok: one highest broad-purchase card and a ready-to-send response
  - no_qualifying_candidate: no explicit broad-purchase rate was found
  - tie_requires_resolution: multiple products share the highest rate
  - invalid_input: input did not conform to the documented schema

Only rates explicitly stated for all purchases, all eligible purchases, eligible
spend, or everyday purchases are ranked. Category-specific rates are not ranked.
"""

import json
import math
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

NUMBER = r"(\d+(?:\.\d+)?)"
TITLE_NAME = re.compile(r"^\s*([^:\n]+?)\s*:")

# Each expression requires both a percentage and an explicit broad spending scope.
BROAD_RATE_PATTERNS = (
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + NUMBER
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?eligible\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you\s+)?earn(?:s)?\s+" + NUMBER
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+all\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcash\s*back\s+on\s+all\s+(?:eligible\s+)?(?:purchases|spend)\s*:\s*"
        + NUMBER
        + r"\s*%",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b" + NUMBER
        + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?everyday\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
)


def invalid(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "error": message}


def card_name(title: str) -> Optional[str]:
    match = TITLE_NAME.match(title)
    if not match:
        return None
    result = match.group(1).strip()
    return result or None


def broad_rates(content: str) -> List[float]:
    """Return distinct finite, nonnegative broad-purchase rates in a document."""
    found = set()
    for pattern in BROAD_RATE_PATTERNS:
        for match in pattern.finditer(content):
            rate = float(match.group(1))
            if math.isfinite(rate) and rate >= 0:
                found.add(rate)
    return sorted(found)


def format_percent(rate: float) -> str:
    rendered = f"{rate:.10f}".rstrip("0").rstrip(".")
    return rendered if "." in rendered else rendered + ".0"


def parse_documents(payload: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None, invalid("top-level input must be an object")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return None, invalid("documents must be an array")

    # Map one consistent broad rate per product. Repeated product documents with
    # the same rate are normal; contradictory broad rates need source resolution.
    by_product: Dict[str, set] = {}
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            return None, invalid(f"documents[{index}] must be an object")
        title = document.get("title")
        content = document.get("content")
        if not isinstance(title, str) or not title.strip():
            return None, invalid(f"documents[{index}].title must be a nonempty string")
        if not isinstance(content, str):
            return None, invalid(f"documents[{index}].content must be a string")

        name = card_name(title)
        if name is None:
            continue
        rates = broad_rates(content)
        if rates:
            by_product.setdefault(name, set()).update(rates)

    candidates: List[Dict[str, Any]] = []
    for name, rates in by_product.items():
        if len(rates) != 1:
            return None, invalid(
                f"conflicting broad-purchase cash-back rates documented for {name}"
            )
        candidates.append(
            {
                "product_name": name,
                "earn_rate_percent": rates.pop(),
                "earn_scope": "all_eligible_purchases",
            }
        )
    return candidates, None


def select(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "status": "no_qualifying_candidate",
            "reason": "No explicit cash-back rate for broad eligible purchases was found.",
            "qualifying_candidates": [],
        }

    highest = max(candidate["earn_rate_percent"] for candidate in candidates)
    leaders = [
        candidate for candidate in candidates if candidate["earn_rate_percent"] == highest
    ]
    if len(leaders) != 1:
        return {
            "status": "tie_requires_resolution",
            "highest_earn_rate_percent": highest,
            "tied_candidates": leaders,
            "qualifying_candidates": candidates,
        }

    winner = leaders[0]
    rate = format_percent(winner["earn_rate_percent"])
    response = (
        f"I recommend the {winner['product_name']}. It earns {rate}% cash back "
        "on all eligible purchases, the highest documented rate for everyday spending."
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
