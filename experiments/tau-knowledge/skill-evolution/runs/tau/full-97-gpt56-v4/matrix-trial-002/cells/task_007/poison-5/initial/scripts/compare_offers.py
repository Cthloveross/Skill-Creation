#!/usr/bin/env python3
"""Classify and normalize promotional credit-card offers from JSON stdin."""

import json
import sys
from datetime import date
from typing import Any, Dict, List, Optional


def parse_date(value: Any, field: str) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def nonnegative_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field} must be a nonnegative number")
    return float(value)


def normalized_value(offer: Dict[str, Any]) -> Optional[float]:
    amount = nonnegative_number(offer.get("reward_amount"), "reward_amount")
    unit = offer.get("reward_unit")
    if unit in ("statement_credit", "cash_back"):
        return amount
    if unit == "points":
        rate = offer.get("point_value_dollars")
        if rate is None:
            return None
        return amount * nonnegative_number(rate, "point_value_dollars")
    return None


def validate_offer(raw: Any, index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"offers[{index}] must be an object")
    card = raw.get("card")
    if not isinstance(card, str) or not card.strip():
        raise ValueError(f"offers[{index}].card must be a nonempty string")
    start = parse_date(raw.get("start_date"), "start_date")
    end = parse_date(raw.get("end_date"), "end_date")
    if start and end and start > end:
        raise ValueError(f"offers[{index}] has start_date after end_date")
    nonnegative_number(raw.get("reward_amount"), "reward_amount")
    unit = raw.get("reward_unit")
    if unit not in ("statement_credit", "cash_back", "points", "other"):
        raise ValueError(f"offers[{index}].reward_unit is unsupported")
    if raw.get("point_value_dollars") is not None:
        nonnegative_number(raw["point_value_dollars"], "point_value_dollars")
    for field in ("spend_requirement", "qualification_months", "annual_fee_dollars"):
        if raw.get(field) is not None:
            nonnegative_number(raw[field], field)
    restrictions = raw.get("restrictions", [])
    if not isinstance(restrictions, list) or not all(isinstance(x, str) for x in restrictions):
        raise ValueError(f"offers[{index}].restrictions must be an array of strings")
    return raw


def render_offer(offer: Dict[str, Any]) -> Dict[str, Any]:
    value = normalized_value(offer)
    return {
        "card": offer["card"],
        "reward_amount": offer["reward_amount"],
        "reward_unit": offer["reward_unit"],
        "cash_equivalent_dollars": value,
        "spend_requirement": offer.get("spend_requirement"),
        "qualification_months": offer.get("qualification_months"),
        "restrictions": offer.get("restrictions", []),
        "annual_fee_dollars": offer.get("annual_fee_dollars"),
        "fee_waived_by_offer": bool(offer.get("fee_waived_by_offer", False)),
        "start_date": offer.get("start_date"),
        "end_date": offer.get("end_date"),
    }


def main() -> None:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    comparison = parse_date(payload.get("comparison_date"), "comparison_date")
    if comparison is None:
        raise ValueError("comparison_date is required")
    offers = payload.get("offers")
    if not isinstance(offers, list):
        raise ValueError("offers must be an array")

    current: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []
    unconfirmed: List[Dict[str, Any]] = []
    for index, raw in enumerate(offers):
        offer = validate_offer(raw, index)
        start = parse_date(offer.get("start_date"), "start_date")
        end = parse_date(offer.get("end_date"), "end_date")
        rendered = render_offer(offer)
        if start is None or end is None:
            unconfirmed.append(rendered)
        elif comparison < start:
            unconfirmed.append(rendered)
        elif comparison > end:
            expired.append(rendered)
        else:
            current.append(rendered)

    # Known cash values sort first, descending; unknown conversions remain visible last.
    current.sort(key=lambda x: (x["cash_equivalent_dollars"] is not None,
                                x["cash_equivalent_dollars"] or 0), reverse=True)
    highest = next((x for x in current if x["cash_equivalent_dollars"] is not None), None)
    print(json.dumps({
        "comparison_date": comparison.isoformat(),
        "current_offers": current,
        "unconfirmed_offers": unconfirmed,
        "expired_offers": expired,
        "highest_current_cash_equivalent": highest,
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
