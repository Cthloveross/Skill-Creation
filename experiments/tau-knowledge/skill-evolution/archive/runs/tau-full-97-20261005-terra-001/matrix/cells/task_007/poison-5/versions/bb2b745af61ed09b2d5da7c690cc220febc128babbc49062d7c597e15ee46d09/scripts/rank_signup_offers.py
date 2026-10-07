#!/usr/bin/env python3
"""Rank normalized, documented credit-card sign-up offers.

Read one JSON object from stdin and emit one JSON object to stdout. This script
uses only the Python standard library. See SKILL.md for the schema.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def parse_date(value, field, context):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{context}: {field} must be an ISO date string or null")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{context}: {field} must be YYYY-MM-DD") from exc


def decimal_nonnegative(value, field, card, allow_null=False):
    if value is None and allow_null:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{card}: {field} must be a nonnegative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{card}: {field} must be a nonnegative number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{card}: {field} must be a nonnegative number")
    return result


def dollars(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def normalize(raw, as_of_date):
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

    cash = decimal_nonnegative(raw.get("cash_bonus", 0), "cash_bonus", card)
    points = decimal_nonnegative(raw.get("points_bonus", 0), "points_bonus", card)
    point_value = decimal_nonnegative(
        raw.get("point_value_usd"), "point_value_usd", card, allow_null=True
    )
    waiver = decimal_nonnegative(raw.get("fee_waiver_value", 0), "fee_waiver_value", card)
    spend = decimal_nonnegative(raw.get("required_spend", 0), "required_spend", card)
    months = decimal_nonnegative(
        raw.get("qualification_months", 0), "qualification_months", card
    )
    notes = raw.get("eligibility_notes", [])
    if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
        raise ValueError(f"{card}: eligibility_notes must be an array of strings")

    # Both boundaries are required before availability is called confirmed.
    availability_confirmed = start is not None and end is not None
    within_known_bounds = (start is None or as_of_date >= start) and (
        end is None or as_of_date <= end
    )
    point_total = points * point_value if points and point_value is not None else None
    total = cash + waiver + (point_total if point_total is not None else Decimal("0"))

    offer = {
        "card": card,
        "source_id": source_id,
        "window_start": raw.get("window_start"),
        "window_end": raw.get("window_end"),
        "cash_bonus": dollars(cash),
        "points_bonus": float(points),
        "point_value_usd": None if point_value is None else float(point_value),
        "points_value_usd": None if point_total is None else dollars(point_total),
        "fee_waiver_value": dollars(waiver),
        "required_spend": dollars(spend),
        "qualification_months": float(months),
        "eligibility_notes": notes,
        "availability_confirmed": availability_confirmed,
        "total_disclosed_incentive_usd": dollars(total),
    }
    if points > 0 and point_total is None:
        offer["unvalued_points_warning"] = (
            "Points are excluded from the monetary total because no documented "
            "USD-per-point conversion was supplied."
        )
    return offer, within_known_bounds, availability_confirmed


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

        ranked = []
        excluded = []
        unknown = []
        for raw in offers:
            offer, within_bounds, confirmed = normalize(raw, as_of)
            if not within_bounds:
                offer["exclusion_reason"] = "outside_documented_offer_window"
                excluded.append(offer)
            elif not confirmed:
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
        json.dump(
            {
                "as_of_date": as_of.isoformat(),
                "ranked_current_offers": ranked,
                "excluded_offers": excluded,
                "availability_unknown_offers": unknown,
            },
            sys.stdout,
            sort_keys=True,
        )
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
