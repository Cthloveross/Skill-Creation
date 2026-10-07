#!/usr/bin/env python3
"""Compare card reward estimates from JSON provided on stdin.

The program is deterministic and makes no network, account, or application calls.
See SKILL.md for the input and output schema.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def decimal_value(value, field):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if not parsed.is_finite():
        raise ValueError(f"{field} must be finite")
    return parsed


def text(value):
    return str(value or "").strip().casefold()


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def compare(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    amount = decimal_value(payload.get("amount"), "amount")
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty array")

    merchant = text(payload.get("merchant"))
    category = text(payload.get("expected_category"))
    results = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"cards[{index}] must be an object")
        name = str(card.get("name", "")).strip()
        if not name:
            raise ValueError(f"cards[{index}].name is required")
        base = decimal_value(card.get("base_rate_percent"), f"cards[{index}].base_rate_percent")
        if base < 0:
            raise ValueError("reward rates cannot be negative")
        bonus = card.get("bonus_rates_percent", {})
        excluded = card.get("excluded_merchants", {})
        if not isinstance(bonus, dict) or not isinstance(excluded, dict):
            raise ValueError("bonus_rates_percent and excluded_merchants must be objects")

        rate = base
        reason = "base_rate"
        matched_exclusion = None
        for excluded_name, excluded_rate in excluded.items():
            if merchant and text(excluded_name) == merchant:
                rate = decimal_value(excluded_rate, "excluded merchant rate")
                if rate < 0:
                    raise ValueError("reward rates cannot be negative")
                reason = "merchant_exclusion"
                matched_exclusion = str(excluded_name)
                break
        if matched_exclusion is None and category:
            for bonus_category, bonus_rate in bonus.items():
                if text(bonus_category) == category:
                    rate = decimal_value(bonus_rate, "bonus rate")
                    if rate < 0:
                        raise ValueError("reward rates cannot be negative")
                    reason = "category_bonus"
                    break

        maximum = card.get("max_limit")
        if maximum is None or str(maximum).strip() == "":
            capacity = "unknown"
            feasible = False
        else:
            max_limit = decimal_value(maximum, f"cards[{index}].max_limit")
            if max_limit < 0:
                raise ValueError("max_limit cannot be negative")
            capacity = "sufficient" if max_limit >= amount else "insufficient"
            feasible = max_limit >= amount
        reward = amount * rate / Decimal("100")
        results.append({
            "name": name,
            "published_maximum_capacity": capacity,
            "eligible_for_ranked_single_charge_comparison": feasible,
            "applied_rate_percent": str(rate),
            "rate_basis": reason,
            "matched_exclusion": matched_exclusion,
            "estimated_cash_back": money(reward),
            "category_is_assumption": bool(category) and reason == "category_bonus"
        })

    ranked = sorted(
        (item for item in results if item["eligible_for_ranked_single_charge_comparison"]),
        key=lambda item: (Decimal(item["estimated_cash_back"]), item["name"].casefold()),
        reverse=True,
    )
    return {
        "amount": money(amount),
        "merchant": payload.get("merchant"),
        "expected_category": payload.get("expected_category"),
        "results": results,
        "ranked_feasible_cards": ranked,
        "notice": "Published maximum capacity does not guarantee approval, an assigned credit limit, or merchant-category qualification."
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(compare(payload), separators=(",", ":"), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
