#!/usr/bin/env python3
"""Normalize documented card-offer facts supplied as JSON on stdin.

The program performs no retrieval. Output is JSON:
{"offers": [...], "excluded_count": int, "as_of_date": str|null}
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def parse_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def money_product(a, b):
    if a is None or b is None:
        return None
    try:
        return float((Decimal(str(a)) * Decimal(str(b))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("offers"), list):
        raise ValueError("input must be an object containing an offers array")
    personal_only = bool(payload.get("personal_only", False))
    as_of_raw = payload.get("as_of_date")
    as_of = parse_date(as_of_raw)
    result, excluded = [], 0
    for offer in payload["offers"]:
        if not isinstance(offer, dict):
            continue
        category = offer.get("category")
        if personal_only and category != "personal":
            excluded += 1
            continue
        start, end = parse_date(offer.get("offer_start")), parse_date(offer.get("offer_end"))
        active = None
        if as_of is not None and start is not None and end is not None:
            active = start <= as_of <= end
        points = offer.get("bonus_points")
        value = offer.get("point_value_dollars")
        result.append({
            "name": offer.get("name"),
            "category": category,
            "bonus_points": points,
            "point_value_dollars": value,
            "bonus_value_dollars": money_product(points, value),
            "annual_fee_dollars": offer.get("annual_fee_dollars"),
            "spend_requirement_dollars": offer.get("spend_requirement_dollars"),
            "period": offer.get("period"),
            "offer_start": offer.get("offer_start"),
            "offer_end": offer.get("offer_end"),
            "active_as_of_date": active,
            "conditions": offer.get("conditions") if isinstance(offer.get("conditions"), list) else []
        })
    return {"offers": result, "excluded_count": excluded, "as_of_date": as_of_raw if as_of else None}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
