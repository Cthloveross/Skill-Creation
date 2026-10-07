#!/usr/bin/env python3
"""Rank documented cards by flat everyday cash-back rate.

Read JSON from stdin and write JSON to stdout. See SKILL.md for schemas.
"""

import json
import sys
from typing import Any, Dict, List


def fail(message: str) -> None:
    print(json.dumps({"error": message}))
    raise SystemExit(2)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_card(card: Any, index: int) -> Dict[str, Any]:
    if not isinstance(card, dict):
        fail(f"cards[{index}] must be an object")
    required = ("name", "personal", "cash_back", "annual_fee_usd", "everyday_cash_back_pct")
    for key in required:
        if key not in card:
            fail(f"cards[{index}] is missing {key}")
    if not isinstance(card["name"], str) or not card["name"].strip():
        fail(f"cards[{index}].name must be a nonempty string")
    if not isinstance(card["personal"], bool) or not isinstance(card["cash_back"], bool):
        fail(f"cards[{index}] personal and cash_back must be booleans")
    for key in ("annual_fee_usd", "everyday_cash_back_pct"):
        if not is_number(card[key]) or card[key] < 0:
            fail(f"cards[{index}].{key} must be a non-negative number")
    for key in ("requirements", "notes"):
        if key in card and (
            not isinstance(card[key], list) or not all(isinstance(x, str) for x in card[key])
        ):
            fail(f"cards[{index}].{key} must be an array of strings")
    return card


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        fail("input must be an object containing a cards array")

    require_no_fee = payload.get("require_no_annual_fee", True)
    if not isinstance(require_no_fee, bool):
        fail("require_no_annual_fee must be a boolean")

    cards = [validate_card(card, i) for i, card in enumerate(payload["cards"])]
    candidates = [
        card for card in cards
        if card["personal"] and card["cash_back"]
        and (not require_no_fee or card["annual_fee_usd"] == 0)
    ]
    candidates.sort(key=lambda c: (-c["everyday_cash_back_pct"], c["annual_fee_usd"], c["name"]))

    warnings: List[str] = []
    if not candidates:
        warnings.append("No supplied card meets the requested personal cash-back and fee criteria.")
        result = {"eligible_candidates": [], "top_rate_pct": None, "recommendations": [], "warnings": warnings}
    else:
        top_rate = candidates[0]["everyday_cash_back_pct"]
        recommendations = [card for card in candidates if card["everyday_cash_back_pct"] == top_rate]
        for card in recommendations:
            if card.get("requirements"):
                warnings.append(f"{card['name']} has requirements that must be confirmed before recommending it unconditionally.")
        result = {
            "eligible_candidates": candidates,
            "top_rate_pct": top_rate,
            "recommendations": recommendations,
            "warnings": warnings,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
