#!/usr/bin/env python3
"""Select the highest explicitly documented broad-purchase cash-back card.

Input JSON:
  {"documents": [{"title": str, "content": str}, ...]}

Output JSON statuses:
  ok, no_qualifying_candidate, tie_requires_resolution, invalid_input.

Only earn rates paired with an explicit broad purchase scope are ranked. Category
bonuses, promotions, fees, APRs, conversion rates, and illustrative calculations
are excluded.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

TITLE_PREFIX = re.compile(r"^\s*([^:\n]+?)\s*:")
RATE = r"(?P<rate>\d+(?:\.\d+)?)"

# pattern, normalized broad scope, customer-facing scope
BROAD_RATE_PATTERNS = (
    (
        re.compile(
            r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + RATE
            + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+all\s+eligible\s+"
            r"(?:purchases|spend)\b",
            re.IGNORECASE,
        ),
        "all_eligible_purchases",
        "all eligible purchases",
    ),
    (
        re.compile(
            r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + RATE
            + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+eligible\s+"
            r"(?:purchases|spend)\b",
            re.IGNORECASE,
        ),
        "eligible_purchases",
        "eligible purchases",
    ),
    (
        re.compile(
            r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + RATE
            + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+all\s+"
            r"(?:purchases|spend|categories)\b",
            re.IGNORECASE,
        ),
        "all_purchases",
        "all purchases",
    ),
    (
        re.compile(
            r"\bcash\s*back\s+on\s+all\s+(?:eligible\s+)?"
            r"(?:purchases|spend|categories)\s*:\s*" + RATE + r"\s*%\b",
            re.IGNORECASE,
        ),
        "all_purchases",
        "all purchases",
    ),
    (
        re.compile(
            r"\b(?:you\s+)?earn(?:s)?\s+(?:rewards\s+at\s+)?" + RATE
            + r"\s*%\s*(?:cash\s*back|back)?\s+on\s+(?:all\s+)?everyday\s+"
            r"(?:purchases|spend)\b",
            re.IGNORECASE,
        ),
        "everyday_purchases",
        "everyday purchases",
    ),
)


def invalid(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "error": message}


def product_name(title: str) -> Optional[str]:
    """Get the product portion of a conventional 'Product: topic' title."""
    match = TITLE_PREFIX.match(title)
    if not match:
        return None
    name = match.group(1).strip()
    return name or None


def parse_rate(text: str) -> Optional[Decimal]:
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError):
        return None
    if not value.is_finite() or value < 0:
        return None
    return value


def rates_in_document(content: str) -> List[Tuple[Decimal, str, str]]:
    """Return unique (rate, scope-code, response-scope) broad earn statements."""
    found: List[Tuple[Decimal, str, str]] = []
    seen = set()
    for pattern, scope_code, response_scope in BROAD_RATE_PATTERNS:
        for match in pattern.finditer(content):
            rate = parse_rate(match.group("rate"))
            if rate is None:
                continue
            item = (rate, scope_code, response_scope)
            if item not in seen:
                seen.add(item)
                found.append(item)
    return found


def display_rate(rate: Decimal) -> str:
    text = format(rate.normalize(), "f")
    if "." not in text:
        return text + ".0"
    text = text.rstrip("0").rstrip(".")
    return text if "." in text else text + ".0"


def parse_candidates(payload: Any) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return None, invalid("top-level input must be an object")
    documents = payload.get("documents")
    if not isinstance(documents, list):
        return None, invalid("documents must be an array")

    by_product: Dict[str, List[Tuple[Decimal, str, str]]] = {}
    source_titles: Dict[str, List[str]] = {}

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
        if name is None:
            continue
        for earning in rates_in_document(content):
            if earning not in by_product.setdefault(name, []):
                by_product[name].append(earning)
                source_titles.setdefault(name, []).append(title)

    candidates: List[Dict[str, Any]] = []
    for name in sorted(by_product):
        earnings = by_product[name]
        distinct_rates = {earning[0] for earning in earnings}
        if len(distinct_rates) != 1:
            return None, invalid("conflicting broad-purchase cash-back rates documented for " + name)
        rate = next(iter(distinct_rates))
        # Prefer the strongest explicit wording when multiple statements give the
        # same rate; it does not affect ranking.
        scope_order = {"all_eligible_purchases": 0, "all_purchases": 1,
                       "eligible_purchases": 2, "everyday_purchases": 3}
        earning = sorted(earnings, key=lambda item: scope_order.get(item[1], 99))[0]
        candidates.append({
            "product_name": name,
            "earn_rate_percent": float(rate),
            "earn_scope": earning[1],
            "response_scope": earning[2],
            "source_titles": source_titles[name],
        })
    return candidates, None


def select(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "status": "no_qualifying_candidate",
            "reason": "No explicit broad-purchase cash-back earn rate was found.",
            "qualifying_candidates": [],
        }

    highest = max(Decimal(str(item["earn_rate_percent"])) for item in candidates)
    leaders = [item for item in candidates if Decimal(str(item["earn_rate_percent"])) == highest]
    if len(leaders) != 1:
        return {
            "status": "tie_requires_resolution",
            "highest_earn_rate_percent": float(highest),
            "tied_candidates": leaders,
            "qualifying_candidates": candidates,
        }

    winner = leaders[0]
    response = (
        f"I recommend the {winner['product_name']}. It earns "
        f"{display_rate(highest)}% cash back on {winner['response_scope']}, "
        "making it the highest documented rate for everyday spending."
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

    candidates, failure = parse_candidates(payload)
    result = failure if failure is not None else select(candidates or [])
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
