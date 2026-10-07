#!/usr/bin/env python3
"""Select the highest flat everyday cash-back offer from JSON on stdin.

Input schema:
  {"candidates": [{
      "product_name": str,
      "earn_rate_percent": number,
      "earn_scope": "all_eligible_purchases" | "category_limited" |
                    "conditional" | "unknown",
      "eligibility_or_access": str (optional),
      "supporting_facts": [str] (optional)
  }]}

Output schema:
  {"status": "ok", "recommendation": object, "qualifying_candidates": [object]}
  or a structured no-candidate/tie/error result.
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


def error(message: str) -> Dict[str, Any]:
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
        return False, f"candidates[{index}].earn_rate_percent must be a finite nonnegative number"
    scope = candidate.get("earn_scope")
    if scope not in VALID_SCOPES:
        return False, f"candidates[{index}].earn_scope is invalid"
    access = candidate.get("eligibility_or_access")
    if access is not None and not isinstance(access, str):
        return False, f"candidates[{index}].eligibility_or_access must be a string when supplied"
    facts = candidate.get("supporting_facts")
    if facts is not None and (not isinstance(facts, list) or not all(isinstance(x, str) for x in facts)):
        return False, f"candidates[{index}].supporting_facts must be an array of strings when supplied"
    return True, ""


def clean_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Return only stable, response-safe fields and normalize numeric rate."""
    result: Dict[str, Any] = {
        "product_name": candidate["product_name"].strip(),
        "earn_rate_percent": float(candidate["earn_rate_percent"]),
        "earn_scope": candidate["earn_scope"],
    }
    if candidate.get("eligibility_or_access"):
        result["eligibility_or_access"] = candidate["eligibility_or_access"].strip()
    if candidate.get("supporting_facts"):
        result["supporting_facts"] = candidate["supporting_facts"]
    return result


def select(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return error("top-level input must be an object")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return error("candidates must be an array")

    cleaned: List[Dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        valid, message = validate_candidate(candidate, index)
        if not valid:
            return error(message)
        cleaned.append(clean_candidate(candidate))

    qualifying = [
        c for c in cleaned
        if c["earn_scope"] == "all_eligible_purchases"
    ]
    if not qualifying:
        return {
            "status": "no_qualifying_candidate",
            "reason": "No candidate has a documented flat rate on all eligible purchases.",
            "qualifying_candidates": [],
        }

    highest_rate = max(c["earn_rate_percent"] for c in qualifying)
    leaders = [c for c in qualifying if c["earn_rate_percent"] == highest_rate]
    # Preserve source order for transparency; never manufacture a rate-based winner from a tie.
    if len(leaders) != 1:
        return {
            "status": "tie_requires_resolution",
            "highest_earn_rate_percent": highest_rate,
            "tied_candidates": leaders,
            "qualifying_candidates": qualifying,
        }

    return {
        "status": "ok",
        "recommendation": leaders[0],
        "qualifying_candidates": qualifying,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(error(f"invalid JSON: {exc.msg}"), sort_keys=True))
        return
    print(json.dumps(select(payload), sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
