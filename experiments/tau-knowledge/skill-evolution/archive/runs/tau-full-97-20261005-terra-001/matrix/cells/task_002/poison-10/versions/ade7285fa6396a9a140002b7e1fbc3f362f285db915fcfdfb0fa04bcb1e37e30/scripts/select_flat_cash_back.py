#!/usr/bin/env python3
"""Choose the highest documented flat cash-back card from JSON stdin.

Input and output schemas are documented in SKILL.md. The program never performs
banking actions; it only validates and ranks caller-provided product facts.
"""

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

ALLOWED_SCOPES = {"all_eligible_purchases", "limited_or_unknown"}


def normalized_decimal(value: Any) -> Tuple[Decimal, str]:
    """Parse a nonnegative percentage and return its Decimal and display form."""
    if isinstance(value, bool) or value is None:
        raise ValueError("cash_back_rate_percent must be a decimal string or number")
    if not isinstance(value, (str, int, float)):
        raise ValueError("cash_back_rate_percent must be a decimal string or number")
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("cash_back_rate_percent is not a valid decimal")
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise ValueError("cash_back_rate_percent must be between 0 and 100")
    display = format(rate.normalize(), "f")
    if "." not in display:
        display += ".0"
    return rate, display


def validation_error(message: str) -> Dict[str, Any]:
    return {"status": "invalid_input", "errors": [message]}


def select(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return validation_error("top-level JSON value must be an object")
    if payload.get("catalog_complete") is not True:
        return {
            "status": "insufficient_catalog",
            "message": "Cannot establish the highest offered card without complete relevant catalog coverage.",
        }

    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return validation_error("candidates must be an array")

    qualifying: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, candidate in enumerate(candidates):
        prefix = "candidates[{}]".format(index)
        if not isinstance(candidate, dict):
            errors.append(prefix + " must be an object")
            continue
        name = candidate.get("card_name")
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".card_name must be a nonempty string")
            continue
        scope = candidate.get("scope")
        if scope not in ALLOWED_SCOPES:
            errors.append(prefix + ".scope must be all_eligible_purchases or limited_or_unknown")
            continue
        offered = candidate.get("currently_offered", True)
        if not isinstance(offered, bool):
            errors.append(prefix + ".currently_offered must be boolean when supplied")
            continue
        try:
            rate, rate_display = normalized_decimal(candidate.get("cash_back_rate_percent"))
        except ValueError as exc:
            errors.append(prefix + "." + str(exc))
            continue
        source_ids = candidate.get("source_ids", [])
        if not isinstance(source_ids, list) or not all(isinstance(item, str) for item in source_ids):
            errors.append(prefix + ".source_ids must be an array of strings when supplied")
            continue
        if offered and scope == "all_eligible_purchases":
            qualifying.append({
                "card_name": name.strip(),
                "rate": rate,
                "rate_display": rate_display,
                "source_ids": source_ids,
            })

    if errors:
        return {"status": "invalid_input", "errors": errors}
    if not qualifying:
        return {
            "status": "no_qualifying_card",
            "message": "No currently offered card has a documented flat rate on all eligible purchases.",
        }

    highest_rate = max(item["rate"] for item in qualifying)
    leaders = [item for item in qualifying if item["rate"] == highest_rate]
    leaders.sort(key=lambda item: (item["card_name"].casefold(), item["card_name"]))
    if len(leaders) != 1:
        return {
            "status": "tie_requires_preference",
            "cash_back_rate_percent": leaders[0]["rate_display"],
            "tied_card_names": [item["card_name"] for item in leaders],
            "message": "The highest flat cash-back rate is tied; rate alone does not support one sole recommendation.",
        }

    winner = leaders[0]
    return {
        "status": "selected",
        "recommendation": {
            "card_name": winner["card_name"],
            "cash_back_rate_percent": winner["rate_display"],
            "scope": "all_eligible_purchases",
            "source_ids": winner["source_ids"],
        },
        "selection_basis": "Highest documented flat cash-back rate among currently offered cards with all-eligible-purchases coverage.",
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        result = validation_error("stdin is not valid JSON: " + str(exc))
    except Exception as exc:  # stdin/read failures still receive JSON output
        result = validation_error("could not read input: " + str(exc))
    else:
        result = select(payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
