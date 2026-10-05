#!/usr/bin/env python3
"""Rank normalized, documented signup offers.

Reads one JSON object from stdin and writes one JSON object to stdout.  Uses only
Python's standard library.  See SKILL.md for the input and output schema.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_PLACES = Decimal("0.01")


def parse_date(value, field, card):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{card}: {field} must be an ISO date string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{card}: {field} is not YYYY-MM-DD") from exc


def nonnegative_decimal(value, field, card, allow_null=False):
    if value is None and allow_null:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{card}: {field} must be a nonnegative number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{card}: {field} must be a nonnegative number") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{card}: {field} must be a nonnegative number")
    return amount


def money(value):
    return float(value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP))


def normalize_offer(raw, as_of):
    if not isinstance(raw, dict):
        raise ValueError("Each offer must be an object")
    card = raw.get("card")
    source_id = raw.get("source_id")
    if not isinstance(card, str) or not card.strip():
        raise ValueError("Each offer requires a nonempty card")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"{card}: source_id is required")

    start = parse_date(raw.get("window_start"), "window_start", card)
    end = parse_date(raw.get("window_end"), "window_end", card)
    if start and end and start > end:
        raise ValueError(f"{card}: window_start cannot be after window_end")

    cash = nonnegative_decimal(raw.get("cash_bonus", 0), "cash_bonus", card)
    points = nonnegative_decimal(raw.get("points_bonus", 0), "points_bonus", card)
    point_value = nonnegative_decimal(
        raw.get("point_value_usd"), "point_value_usd", card, allow_null=True
    )
    waiver = nonnegative_decimal(raw.get("fee_waiver_value", 0), "fee_waiver_value", card)
    spend = nonnegative_decimal(raw.get("required_spend", 0), "required_spend", card)
    months = nonnegative_decimal(
        raw.get("qualification_months", 0), "qualification_months", card
    )
    notes = raw.get("eligibility_notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise ValueError(f"{card}: eligibility_notes must be an array of strings")

    # A points award has no monetary ranking value unless a documented conversion exists.
    points_value = points * point_value if points and point_value is not None else None
    current = (start is None or as_of >= start) and (end is None or as_of <= end)
    availability_known = start is not None and end is not None

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
        "availability_confirmed": availability_known,
    }
    if points_value is None and points > 0:
        result["unvalued_points_warning"] = (
            "Points are not included in the monetary total because no documented "
            "USD-per-point value was supplied."
        )
    ranking_value = cash + waiver + (points_value or Decimal("0"))
    result["total_disclosed_incentive_usd"] = money(ranking_value)
    return result, current, availability_known


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        as_of = parse_date(payload.get("as_of_date"), "as_of_date", "input")
        if as_of is None:
            raise ValueError("as_of_date is required")
        offers = payload.get("offers")
        if not isinstance(offers, list):
            raise ValueError("offers must be an array")
        include_unknown = payload.get("include_availability_unknown", False)
        if not isinstance(include_unknown, bool):
            raise ValueError("include_availability_unknown must be boolean")

        ranked, excluded, unknown = [], [], []
        for raw in offers:
            offer, current, availability_known = normalize_offer(raw, as_of)
            if not current:
                offer["exclusion_reason"] = "outside_documented_offer_window"
                excluded.append(offer)
            elif not availability_known:
                offer["availability_note"] = "Documented offer window is incomplete or absent."
                unknown.append(offer)
                if include_unknown:
                    ranked.append(offer)
            else:
                ranked.append(offer)

        ranked.sort(
            key=lambda item: (
                -item["total_disclosed_incentive_usd"],
                item["required_spend"],
                item["card"].casefold(),
            )
        )
        output = {
            "as_of_date": as_of.isoformat(),
            "ranked_current_offers": ranked,
            "excluded_offers": excluded,
            "availability_unknown_offers": unknown,
        }
        json.dump(output, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
