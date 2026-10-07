#!/usr/bin/env python3
"""Select the uniquely highest documented flat everyday cash-back card.

Reads the JSON schema documented in SKILL.md from stdin and writes a JSON result
on stdout. This module uses only the Python standard library.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple


def _decimal(value: Any, field: str, index: int) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"cards[{index}].{field} must be a decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"cards[{index}].{field} must be a decimal number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"cards[{index}].{field} must be a nonnegative finite decimal")
    return result


def _text_list(value: Any, field: str, index: int, required: bool = False) -> List[str]:
    if value is None:
        value = []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"cards[{index}].{field} must be a list of nonempty strings")
    if required and not value:
        raise ValueError(f"cards[{index}].{field} must not be empty")
    return [item.strip() for item in value]


def validate_and_filter(payload: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        raise ValueError("input must be an object with a cards array")
    if not payload["cards"]:
        raise ValueError("cards must contain at least one candidate")

    qualifying: List[Dict[str, Any]] = []
    excluded: List[str] = []
    seen_names = set()
    for index, raw in enumerate(payload["cards"]):
        if not isinstance(raw, dict):
            raise ValueError(f"cards[{index}] must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"cards[{index}].name must be a nonempty string")
        name = name.strip()
        if name in seen_names:
            raise ValueError("each candidate name must be unique")
        seen_names.add(name)
        if not isinstance(raw.get("personal"), bool):
            raise ValueError(f"cards[{index}].personal must be boolean")
        if not isinstance(raw.get("applies_to_all_eligible_purchases"), bool):
            raise ValueError(f"cards[{index}].applies_to_all_eligible_purchases must be boolean")
        available = raw.get("ordinary_application_available", True)
        if not isinstance(available, bool):
            raise ValueError(f"cards[{index}].ordinary_application_available must be boolean")
        rate = _decimal(raw.get("cash_back_rate_percent"), "cash_back_rate_percent", index)
        annual_fee = raw.get("annual_fee")
        if annual_fee is not None:
            annual_fee = _decimal(annual_fee, "annual_fee", index)
        candidate = {
            "name": name,
            "cash_back_rate_percent": rate,
            "annual_fee": annual_fee,
            "eligibility_constraints": _text_list(raw.get("eligibility_constraints"), "eligibility_constraints", index),
            "conditions": _text_list(raw.get("conditions"), "conditions", index),
            "evidence": _text_list(raw.get("evidence"), "evidence", index, required=True),
        }
        if raw["personal"] and raw["applies_to_all_eligible_purchases"] and available:
            qualifying.append(candidate)
        else:
            excluded.append(name)
    return qualifying, excluded


def choose(payload: Dict[str, Any]) -> Dict[str, Any]:
    qualifying, excluded = validate_and_filter(payload)
    if not qualifying:
        return {
            "status": "needs_review",
            "reason": "No personal card is documented as ordinarily available with a flat rate on all eligible purchases.",
            "excluded_candidates": excluded,
        }
    highest_rate = max(card["cash_back_rate_percent"] for card in qualifying)
    winners = [card for card in qualifying if card["cash_back_rate_percent"] == highest_rate]
    if len(winners) != 1:
        return {
            "status": "needs_review",
            "reason": "The supplied evidence has a tie for the highest qualifying flat cash-back rate; no source-supported tie-breaker was provided.",
            "tied_card_names": [card["name"] for card in winners],
            "rate_percent": str(highest_rate),
        }
    selected = winners[0]
    recommendation = {
        "name": selected["name"],
        "cash_back_rate_percent": str(selected["cash_back_rate_percent"]),
        "annual_fee": None if selected["annual_fee"] is None else str(selected["annual_fee"]),
        "eligibility_constraints": selected["eligibility_constraints"],
        "conditions": selected["conditions"],
        "evidence": selected["evidence"],
    }
    return {
        "status": "ok",
        "recommendation": recommendation,
        "selection_basis": "Unique highest documented flat cash-back rate on all eligible personal everyday purchases among ordinarily available candidates.",
        "excluded_candidates": excluded,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        result = choose(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"status": "needs_review", "reason": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
