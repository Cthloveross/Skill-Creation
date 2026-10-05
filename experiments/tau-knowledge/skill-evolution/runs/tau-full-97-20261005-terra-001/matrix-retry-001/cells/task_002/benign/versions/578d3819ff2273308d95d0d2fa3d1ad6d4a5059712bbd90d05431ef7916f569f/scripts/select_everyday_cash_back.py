#!/usr/bin/env python3
"""Select the highest documented flat everyday cash-back offer.

Reads JSON from stdin:
  {"candidates": [{
    "product_name": str,
    "earn_rate_percent": number,
    "earn_scope": "all_eligible_purchases" | "category_limited" |
                  "conditional" | "unknown",
    "eligibility_or_access": str (optional),
    "supporting_facts": [str] (optional)
  }]}

Writes JSON to stdout. A unique qualifying winner has status "ok", a
recommendation, and a ready-to-send customer_response. The script deliberately
never ranks category-limited or conditional rates as everyday rates.
"""

import json
import math
import sys
from typing import Any, Dict, List, Tuple

VALID_SCOPES = {
    "all_eligible_purchases",
    "category_limited",
    "conditional",
    "unknown",
}


def invalid(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "error": message}


def validate_candidate(candidate: Any, index: int) -> Tuple[bool, str]:
    if not isinstance(candidate, dict):
        return False, f"candidates[{index}] must be an object"

    name = candidate.get("product_name")
    if not isinstance(name, str) or not name.strip():
        return False, f"candidates[{index}].product_name must be a nonempty string"

    rate = candidate.get("earn_rate_percent")
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        return False, f"candidates[{index}].earn_rate_percent must be a number"
    if not math.isfinite(float(rate)) or float(rate) < 0:
        return False, (
            f"candidates[{index}].earn_rate_percent must be a finite "
            "nonnegative number"
        )

    if candidate.get("earn_scope") not in VALID_SCOPES:
        return False, f"candidates[{index}].earn_scope is invalid"

    access = candidate.get("eligibility_or_access")
    if access is not None and not isinstance(access, str):
        return False, (
            f"candidates[{index}].eligibility_or_access must be a string when supplied"
        )

    facts = candidate.get("supporting_facts")
    if facts is not None and (
        not isinstance(facts, list) or not all(isinstance(item, str) for item in facts)
    ):
        return False, (
            f"candidates[{index}].supporting_facts must be an array of strings "
            "when supplied"
        )
    return True, ""


def clean_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a candidate and preserve only response-safe source fields."""
    cleaned: Dict[str, Any] = {
        "product_name": candidate["product_name"].strip(),
        "earn_rate_percent": float(candidate["earn_rate_percent"]),
        "earn_scope": candidate["earn_scope"],
    }
    if candidate.get("eligibility_or_access"):
        cleaned["eligibility_or_access"] = candidate["eligibility_or_access"].strip()
    if candidate.get("supporting_facts"):
        cleaned["supporting_facts"] = list(candidate["supporting_facts"])
    return cleaned


def format_percent(rate: float) -> str:
    """Render a rate with at least one decimal place and no floating artifacts."""
    rendered = f"{rate:.10f}".rstrip("0").rstrip(".")
    if "." not in rendered:
        rendered += ".0"
    return rendered


def response_for(winner: Dict[str, Any]) -> str:
    return (
        f"I recommend the {winner['product_name']}. It earns "
        f"{format_percent(winner['earn_rate_percent'])}% cash back on all eligible "
        "purchases, the highest documented rate for everyday spending."
    )


def select(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return invalid("top-level input must be an object")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return invalid("candidates must be an array")

    cleaned: List[Dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        is_valid, message = validate_candidate(candidate, index)
        if not is_valid:
            return invalid(message)
        cleaned.append(clean_candidate(candidate))

    qualifying = [
        candidate
        for candidate in cleaned
        if candidate["earn_scope"] == "all_eligible_purchases"
    ]
    if not qualifying:
        return {
            "status": "no_qualifying_candidate",
            "reason": "No candidate has a documented flat rate on all eligible purchases.",
            "qualifying_candidates": [],
        }

    highest_rate = max(candidate["earn_rate_percent"] for candidate in qualifying)
    leaders = [
        candidate
        for candidate in qualifying
        if candidate["earn_rate_percent"] == highest_rate
    ]
    if len(leaders) != 1:
        return {
            "status": "tie_requires_resolution",
            "highest_earn_rate_percent": highest_rate,
            "tied_candidates": leaders,
            "qualifying_candidates": qualifying,
        }

    winner = leaders[0]
    return {
        "status": "ok",
        "recommendation": winner,
        "qualifying_candidates": qualifying,
        "customer_response": response_for(winner),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(invalid(f"invalid JSON: {exc.msg}"), sort_keys=True))
        return
    print(json.dumps(select(payload), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
