#!/usr/bin/env python3
"""Rank extracted, documented credit-card sign-up promotions.

Reads one JSON object from stdin and writes one JSON object to stdout. Uses only
Python's standard library. See SKILL.md for the input and output schemas.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def parse_date(value, label):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO date string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD") from exc


def nonnegative(value, label, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a nonnegative number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a nonnegative number") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} must be a nonnegative number")
    return number


def money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def normalize(raw, as_of):
    if not isinstance(raw, dict):
        raise ValueError("each offer must be an object")
    card = raw.get("card")
    source_id = raw.get("source_id")
    if not isinstance(card, str) or not card.strip():
        raise ValueError("each offer requires a nonempty card")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"{card}: source_id is required")

    start = parse_date(raw.get("window_start"), f"{card}: window_start")
    end = parse_date(raw.get("window_end"), f"{card}: window_end")
    if start and end and start > end:
        raise ValueError(f"{card}: window_start cannot be after window_end")

    cash = nonnegative(raw.get("cash_bonus", 0), f"{card}: cash_bonus")
    points = nonnegative(raw.get("points_bonus", 0), f"{card}: points_bonus")
    point_value = nonnegative(raw.get("point_value_usd"), f"{card}: point_value_usd", nullable=True)
    waiver = nonnegative(raw.get("fee_waiver_value", 0), f"{card}: fee_waiver_value")
    spend = nonnegative(raw.get("required_spend", 0), f"{card}: required_spend")
    months = nonnegative(raw.get("qualification_months", 0), f"{card}: qualification_months")
    notes = raw.get("eligibility_notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise ValueError(f"{card}: eligibility_notes must be an array of strings")

    confirmed = start is not None and end is not None
    in_known_bounds = (start is None or as_of >= start) and (end is None or as_of <= end)
    points_value = points * point_value if points and point_value is not None else None
    total = cash + waiver + (points_value if points_value is not None else Decimal("0"))
    result = {
        "card": card,
        "source_id": source_id,
        "window_start": raw.get("window_start"),
        "window_end": raw.get("window_end"),
        "cash_bonus": money(cash),
        "points_bonus": float(points),
        "point_value_usd": None if point_value is None else float(point_value),
        "points_value_usd": None if points_value is None else money(points_value),
        "fee_waiver_value": money(waiver),
        "required_spend": money(spend),
        "qualification_months": float(months),
        "eligibility_notes": notes,
        "availability_confirmed": confirmed,
        "total_disclosed_incentive_usd": money(total),
    }
    if points > 0 and points_value is None:
        result["unvalued_points_warning"] = "Points were excluded from the monetary total because no documented USD-per-point conversion was supplied."
    return result, confirmed, in_known_bounds


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        as_of = parse_date(payload.get("as_of_date"), "as_of_date")
        if as_of is None:
            raise ValueError("as_of_date is required")
        offers = payload.get("offers")
        if not isinstance(offers, list):
            raise ValueError("offers must be an array")

        ranked, excluded, unknown = [], [], []
        for raw in offers:
            item, confirmed, in_known_bounds = normalize(raw, as_of)
            if not in_known_bounds:
                item["exclusion_reason"] = "outside_documented_offer_window"
                excluded.append(item)
            elif not confirmed:
                item["availability_note"] = "Documented offer window is incomplete or absent."
                unknown.append(item)
            else:
                ranked.append(item)

        ranked.sort(key=lambda item: (-item["total_disclosed_incentive_usd"], item["required_spend"], item["card"].casefold()))
        json.dump({"as_of_date": as_of.isoformat(), "ranked_current_offers": ranked, "excluded_offers": excluded, "availability_unknown_offers": unknown}, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
