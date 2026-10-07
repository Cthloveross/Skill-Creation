#!/usr/bin/env python3
"""Choose the unique highest flat everyday cash-back card.

Read a JSON object from stdin using the schema in SKILL.md and emit one JSON
object on stdout. Uses only the Python standard library.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple


def _decimal(value: Any, field: str, index: int) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError(f"cards[{index}].{field} must be a decimal number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"cards[{index}].{field} must be a decimal number")
    if not number.is_finite() or number < 0:
        raise ValueError(f"cards[{index}].{field} must be a nonnegative finite decimal")
    return number


def _strings(value: Any, field: str, index: int, required: bool = False) -> List[str]:
    if value is None:
        value = []
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"cards[{index}].{field} must be a list of nonempty strings")
    items = [x.strip() for x in value]
    if required and not items:
        raise ValueError(f"cards[{index}].{field} must not be empty")
    return items


def _format_money(amount: Decimal) -> str:
    return f"${amount:.2f}"


def _validate(payload: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        raise ValueError("input must be an object with a cards array")
    if not payload["cards"]:
        raise ValueError("cards must contain at least one candidate")

    qualifying: List[Dict[str, Any]] = []
    excluded: List[str] = []
    names = set()
    for index, raw in enumerate(payload["cards"]):
        if not isinstance(raw, dict):
            raise ValueError(f"cards[{index}] must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"cards[{index}].name must be a nonempty string")
        name = name.strip()
        if name in names:
            raise ValueError("each candidate name must be unique")
        names.add(name)

        if not isinstance(raw.get("personal"), bool):
            raise ValueError(f"cards[{index}].personal must be boolean")
        if not isinstance(raw.get("applies_to_all_eligible_purchases"), bool):
            raise ValueError(f"cards[{index}].applies_to_all_eligible_purchases must be boolean")
        available = raw.get("ordinary_application_available", True)
        if not isinstance(available, bool):
            raise ValueError(f"cards[{index}].ordinary_application_available must be boolean")

        fee_raw = raw.get("annual_fee")
        fee = None if fee_raw is None else _decimal(fee_raw, "annual_fee", index)
        record = {
            "name": name,
            "cash_back_rate_percent": _decimal(raw.get("cash_back_rate_percent"), "cash_back_rate_percent", index),
            "annual_fee": fee,
            "eligibility_constraints": _strings(raw.get("eligibility_constraints"), "eligibility_constraints", index),
            "conditions": _strings(raw.get("conditions"), "conditions", index),
            "evidence": _strings(raw.get("evidence"), "evidence", index, required=True),
        }
        if raw["personal"] and raw["applies_to_all_eligible_purchases"] and available:
            qualifying.append(record)
        else:
            excluded.append(name)
    return qualifying, excluded


def _customer_message(card: Dict[str, Any]) -> str:
    rate = str(card["cash_back_rate_percent"])
    sentences = [
        f"I recommend the {card['name']}.",
        f"It earns {rate}% cash back on all eligible purchases—the highest documented flat rate for everyday spending.",
    ]
    if card["annual_fee"] is not None:
        sentences.append(f"Its documented annual fee is {_format_money(card['annual_fee'])}.")
    if card["eligibility_constraints"]:
        sentences.append("Documented access requirement: " + "; ".join(card["eligibility_constraints"]) + ".")
    if card["conditions"]:
        sentences.append("Rewards conditions: " + "; ".join(card["conditions"]) + ".")
    return " ".join(sentences)


def choose(payload: Any) -> Dict[str, Any]:
    qualifying, excluded = _validate(payload)
    if not qualifying:
        return {
            "status": "needs_review",
            "reason": "No ordinarily available personal card is documented with a flat cash-back rate on all eligible purchases.",
            "excluded_candidates": excluded,
        }

    high_rate = max(card["cash_back_rate_percent"] for card in qualifying)
    winners = [card for card in qualifying if card["cash_back_rate_percent"] == high_rate]
    if len(winners) != 1:
        return {
            "status": "needs_review",
            "reason": "The highest qualifying flat cash-back rate is tied; the supplied terms provide no tie-breaker.",
            "tied_card_names": [card["name"] for card in winners],
            "rate_percent": str(high_rate),
        }

    winner = winners[0]
    recommendation = {
        "name": winner["name"],
        "cash_back_rate_percent": str(winner["cash_back_rate_percent"]),
        "annual_fee": None if winner["annual_fee"] is None else str(winner["annual_fee"]),
        "eligibility_constraints": winner["eligibility_constraints"],
        "conditions": winner["conditions"],
        "evidence": winner["evidence"],
    }
    return {
        "status": "ok",
        "recommendation": recommendation,
        "customer_message": _customer_message(winner),
        "selection_basis": "Unique highest documented flat cash-back rate on all eligible personal everyday purchases.",
        "excluded_candidates": excluded,
    }


def main() -> None:
    try:
        result = choose(json.load(sys.stdin))
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"status": "needs_review", "reason": str(exc)}
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
