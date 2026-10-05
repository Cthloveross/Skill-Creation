#!/usr/bin/env python3
"""Calculate conditional card-reward scenarios.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs
no network, banking, or file-system operations.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List

CENT = Decimal("0.01")


def decimal_value(value: Any, field: str, allow_none: bool = False) -> Decimal | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def capacity_assessment(maximum: Decimal | None, amount: Decimal) -> str:
    if maximum is None:
        return "unknown_no_documented_maximum"
    if maximum < amount:
        return "not_possible_documented_maximum_below_charge"
    return "possible_subject_to_approved_line_available_credit_and_authorization"


def calculate(payload: Dict[str, Any]) -> Dict[str, Any]:
    amount = decimal_value(payload.get("purchase_amount"), "purchase_amount")
    if amount is None or amount <= 0:
        raise ValueError("purchase_amount must be greater than zero")

    ppcu = decimal_value(payload.get("points_per_currency_unit", 100), "points_per_currency_unit")
    if ppcu is None or ppcu <= 0:
        raise ValueError("points_per_currency_unit must be greater than zero")

    offers = payload.get("offers")
    if not isinstance(offers, list) or not offers:
        raise ValueError("offers must be a non-empty list")

    results: List[Dict[str, Any]] = []
    for offer_index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            raise ValueError(f"offers[{offer_index}] must be an object")
        name = offer.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"offers[{offer_index}].name is required")

        maximum = decimal_value(
            offer.get("maximum_credit_limit"),
            f"offers[{offer_index}].maximum_credit_limit",
            allow_none=True,
        )
        if maximum is not None and maximum < 0:
            raise ValueError(f"offers[{offer_index}].maximum_credit_limit cannot be negative")
        annual_fee = decimal_value(offer.get("annual_fee", 0), f"offers[{offer_index}].annual_fee")
        first_year_fee = decimal_value(
            offer.get("first_year_fee", annual_fee),
            f"offers[{offer_index}].first_year_fee",
        )
        if annual_fee is None or annual_fee < 0 or first_year_fee is None or first_year_fee < 0:
            raise ValueError(f"offers[{offer_index}] fees cannot be negative")

        scenarios = offer.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError(f"offers[{offer_index}].scenarios must be a non-empty list")

        assessment = capacity_assessment(maximum, amount)
        for scenario_index, scenario in enumerate(scenarios):
            if not isinstance(scenario, dict):
                raise ValueError(f"scenario {scenario_index} for {name} must be an object")
            label = scenario.get("label")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"scenario {scenario_index} for {name} needs a label")
            rate = decimal_value(scenario.get("rate_pct"), f"scenario {scenario_index} rate_pct")
            if rate is None or rate < 0:
                raise ValueError(f"scenario {scenario_index} for {name} has an invalid rate_pct")

            reward = (amount * rate / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
            # Points represent cents for the covered cash-back products. Keep the
            # returned point count integral when the configured conversion permits it.
            raw_points = reward * ppcu
            reward_points = raw_points.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            conditions = scenario.get("conditions", [])
            if not isinstance(conditions, list) or not all(isinstance(x, str) for x in conditions):
                raise ValueError(f"scenario {scenario_index} for {name} conditions must be a list of strings")

            results.append({
                "card": name,
                "scenario": label,
                "certainty": scenario.get("certainty", "conditional"),
                "rate_pct": str(rate.normalize()),
                "conditions": conditions,
                "documented_maximum_credit_limit": None if maximum is None else money(maximum),
                "capacity_assessment": assessment,
                "cash_back": money(reward),
                "reward_points": int(reward_points),
                "points_per_currency_unit": str(ppcu.normalize()),
                "annual_fee": money(annual_fee),
                "first_year_fee": money(first_year_fee),
                "first_year_net_after_fee": money(reward - first_year_fee),
            })

    results.sort(
        key=lambda row: (
            Decimal(row["first_year_net_after_fee"]),
            Decimal(row["cash_back"]),
        ),
        reverse=True,
    )
    return {
        "ok": True,
        "purchase_amount": money(amount),
        "results": results,
        "notice": "Calculations are conditional and do not establish approval, available credit, merchant coding, or promotional eligibility.",
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(calculate(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
