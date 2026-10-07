#!/usr/bin/env python3
"""Compare first-year card value scenarios.

Reads JSON from stdin and writes JSON to stdout. See SKILL.md for schema.
This program deliberately does not infer MCCs, promotion windows, or approval.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

CENT = Decimal("0.01")


def money(value: Any, field: str, *, allow_negative: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a decimal number") from exc
    if not parsed.is_finite() or (parsed < 0 and not allow_negative):
        raise ValueError(f"{field} must be a finite nonnegative number")
    return parsed.quantize(CENT, rounding=ROUND_HALF_UP)


def percent(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a decimal percentage") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be a finite nonnegative percentage")
    return parsed


def fmt(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def build_result(purchase: Decimal, card: dict[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError(f"cards[{index}] must be an object")
    name = require_text(card.get("name"), f"cards[{index}].name")
    rate = percent(card.get("earning_rate_percent"), f"cards[{index}].earning_rate_percent")
    fee = money(card.get("annual_fee_first_year", 0), f"cards[{index}].annual_fee_first_year")
    bonus = money(card.get("new_account_bonus", 0), f"cards[{index}].new_account_bonus")
    feasible = card.get("feasible")
    if feasible is not None and not isinstance(feasible, bool):
        raise ValueError(f"cards[{index}].feasible must be true, false, or omitted")
    conditions = card.get("conditions", [])
    if not isinstance(conditions, list) or not all(isinstance(x, str) and x.strip() for x in conditions):
        raise ValueError(f"cards[{index}].conditions must be a list of nonempty strings")

    cash_back = (purchase * rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    net_value = (cash_back + bonus - fee).quantize(CENT, rounding=ROUND_HALF_UP)
    status = "infeasible" if feasible is False else ("confirmed" if feasible is True else "unconfirmed")
    return {
        "name": name,
        "purchase_cash_back": fmt(cash_back),
        "new_account_bonus": fmt(bonus),
        "annual_fee_first_year": fmt(fee),
        "first_year_net_value": fmt(net_value),
        "feasibility": status,
        "conditions": [x.strip() for x in conditions],
        "_index": index,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        purchase = money(payload.get("purchase_amount"), "purchase_amount")
        cards = payload.get("cards")
        if not isinstance(cards, list) or not cards:
            raise ValueError("cards must be a nonempty list")
        results = [build_result(purchase, card, i) for i, card in enumerate(cards)]
        status_order = {"confirmed": 0, "unconfirmed": 1, "infeasible": 2}
        ranked = sorted(
            results,
            key=lambda row: (status_order[row["feasibility"]], -Decimal(row["first_year_net_value"]), row["_index"]),
        )
        for row in results:
            row.pop("_index")
        ranking = [row["name"] for row in ranked]
        print(json.dumps({
            "purchase_amount": fmt(purchase),
            "scenarios": results,
            "ranking": ranking,
            "note": "Ranking uses supplied assumptions only; unconfirmed conditions require customer follow-up.",
        }, ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
