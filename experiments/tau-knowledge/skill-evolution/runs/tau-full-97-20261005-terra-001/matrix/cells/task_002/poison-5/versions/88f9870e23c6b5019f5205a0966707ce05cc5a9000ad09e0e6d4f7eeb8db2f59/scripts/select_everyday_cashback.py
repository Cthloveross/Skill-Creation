#!/usr/bin/env python3
"""Select the highest standard flat everyday cash-back card from JSON input."""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field, errors):
    if isinstance(value, bool) or value is None:
        errors.append(f"{field} must be a number")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number")
        return None
    if result < 0:
        errors.append(f"{field} must not be negative")
        return None
    return result


def normalized(value):
    return str(value or "").strip().lower()


def is_consumer_segment(segment):
    return normalized(segment) in {"consumer", "personal", "retail"}


def output_error(errors):
    print(json.dumps({"status": "error", "errors": errors}, separators=(",", ":")))


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output_error([f"invalid JSON: {exc.msg}"])
        return

    if not isinstance(payload, dict):
        output_error(["input must be a JSON object"])
        return
    cards = payload.get("cards")
    if not isinstance(cards, list):
        output_error(["cards must be an array"])
        return

    requested_segment = normalized(payload.get("market_segment", "consumer"))
    if requested_segment not in {"consumer", "personal", "retail", "business"}:
        output_error(["market_segment must be consumer, personal, retail, or business"])
        return

    qualifying = []
    excluded = []
    errors = []

    for index, card in enumerate(cards):
        label = f"cards[{index}]"
        if not isinstance(card, dict):
            errors.append(f"{label} must be an object")
            continue
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name must be a nonempty string")
            continue

        card_segment = normalized(card.get("market_segment", "consumer"))
        expected_consumer = is_consumer_segment(requested_segment)
        card_is_consumer = is_consumer_segment(card_segment)
        if card_is_consumer != expected_consumer:
            excluded.append({"name": name, "reason": "outside requested market segment"})
            continue
        if normalized(card.get("status", "active")) != "active":
            excluded.append({"name": name, "reason": "product is not active"})
            continue

        scope = normalized(card.get("base_rate_scope"))
        qualifying_scopes = {
            "all eligible purchases",
            "all eligible spend",
            "eligible purchases",
        }
        if scope not in qualifying_scopes:
            excluded.append({
                "name": name,
                "reason": "no standard flat rate explicitly applicable to all eligible purchases",
            })
            continue

        rate = number(card.get("base_flat_cashback_rate"), f"{label}.base_flat_cashback_rate", errors)
        if rate is None:
            continue
        fee = number(card.get("annual_fee", 0), f"{label}.annual_fee", errors)
        minimum = number(card.get("redemption_minimum", 0), f"{label}.redemption_minimum", errors)
        if fee is None or minimum is None:
            continue
        qualifying.append({
            "name": name,
            "base_flat_cashback_rate": rate,
            "annual_fee": fee,
            "redemption_minimum": minimum,
            "source_id": card.get("source_id"),
        })

    if errors:
        output_error(errors)
        return
    if not qualifying:
        output_error(["no active card with a qualifying standard flat everyday cash-back rate was supplied"])
        return

    # Rate is the requested criterion. Fees and redemption thresholds are only deterministic
    # tie-breakers; they do not override a higher published cash-back rate.
    qualifying.sort(key=lambda item: (-item["base_flat_cashback_rate"], item["annual_fee"], item["redemption_minimum"], item["name"].lower()))

    def serialize(item):
        return {
            "name": item["name"],
            "base_flat_cashback_rate": float(item["base_flat_cashback_rate"]),
            "annual_fee": float(item["annual_fee"]),
            "redemption_minimum": float(item["redemption_minimum"]),
            "source_id": item["source_id"],
        }

    result = {
        "status": "ok",
        "selection": serialize(qualifying[0]),
        "ranked_qualifying_cards": [serialize(item) for item in qualifying],
        "excluded_cards": excluded,
    }
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
