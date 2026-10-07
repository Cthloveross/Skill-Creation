#!/usr/bin/env python3
"""Extract broad-purchase cash-back candidates from supplied product documents.

Input JSON:
  {"documents": [{"title": str, "content": str}, ...]}

Output JSON has the status and selection fields from select_everyday_cash_back,
plus extracted_candidates. Only explicit rates that apply to all purchases, all
eligible purchases, eligible spend, or everyday purchases are ranked. This is a
conservative text extractor: documents that do not clearly establish a broad rate
are retained as nonqualifying candidates or ignored when they have no rate.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_everyday_cash_back import invalid, select  # noqa: E402

# A product title normally starts with its customer-facing name followed by a colon.
TITLE_NAME = re.compile(r"^\s*([^:\n]+?)\s*:")
NUMBER = r"(\d+(?:\.\d+)?)"

# These patterns require a rate and an explicit broad-purchase scope in the same
# statement. They deliberately do not match category-only rates.
BROAD_RATE_PATTERNS = [
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
        r"\bcash\s*back\s+on\s+all\s+(?:purchases|spend)\s*:\s*" + NUMBER + r"\s*%\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b" + NUMBER + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?everyday\s+(?:purchases|spend)\b",
        re.IGNORECASE,
    ),
]


def product_name(title: str) -> Optional[str]:
    match = TITLE_NAME.match(title)
    if not match:
        return None
    name = match.group(1).strip()
    return name or None


def explicit_broad_rate(content: str) -> Optional[float]:
    """Return the single explicit broad-purchase rate, or None if absent/ambiguous."""
    rates = []
    for pattern in BROAD_RATE_PATTERNS:
        for match in pattern.finditer(content):
            rates.append(float(match.group(1)))
    distinct = sorted(set(rates))
    if len(distinct) == 1:
        return distinct[0]
    # Multiple inconsistent broad rates in one document need human source review.
    return None


def extract(payload: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None, invalid("top-level input must be an object")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return None, invalid("documents must be an array")

    candidates: List[Dict[str, Any]] = []
    for index, document in enumerate(documents):
        if not isinstance(document, dict):
            return None, invalid(f"documents[{index}] must be an object")
        title = document.get("title")
        content = document.get("content")
        if not isinstance(title, str) or not title.strip():
            return None, invalid(f"documents[{index}].title must be a nonempty string")
        if not isinstance(content, str):
            return None, invalid(f"documents[{index}].content must be a string")

        name = product_name(title)
        rate = explicit_broad_rate(content)
        if name is not None and rate is not None:
            candidates.append(
                {
                    "product_name": name,
                    "earn_rate_percent": rate,
                    "earn_scope": "all_eligible_purchases",
                    "supporting_facts": [
                        "Explicit broad-purchase cash-back rate extracted from supplied terms."
                    ],
                }
            )
    return candidates, None


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(invalid(f"invalid JSON: {exc.msg}"), sort_keys=True))
        return

    candidates, error = extract(payload)
    if error is not None:
        print(json.dumps(error, ensure_ascii=False, sort_keys=True))
        return

    result = select({"candidates": candidates})
    result["extracted_candidates"] = candidates
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
