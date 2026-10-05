#!/usr/bin/env python3
"""Calculate an APY composition where checking and card bonus groups do not stack."""
import json
import sys
from decimal import Decimal, InvalidOperation


def parse_rate(value, field):
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a numeric APY percentage") from exc
    if not rate.is_finite() or rate < 0:
        raise ValueError(f"{field} must be a nonnegative finite APY percentage")
    return rate


def candidates(items, field):
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{field} must be a list")
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or "name" not in item or "apy" not in item:
            raise ValueError(f"{field}[{index}] must contain name and apy")
        result.append({
            "name": str(item["name"]),
            "apy": parse_rate(item["apy"], f"{field}[{index}].apy"),
            "eligible": item.get("eligible") is True,
        })
    return result


def select_highest(items):
    eligible = [item for item in items if item["eligible"]]
    if not eligible:
        return None
    # max preserves documented input order as the tie-breaker.
    return max(eligible, key=lambda item: item["apy"])


def render(item):
    if item is None:
        return None
    return {"name": item["name"], "apy": f"{item['apy']:.6f}"}


def main(payload):
    if "base_apy" not in payload:
        raise ValueError("missing required field: base_apy")
    base = parse_rate(payload["base_apy"], "base_apy")
    checking = candidates(payload.get("checking_boosts", []), "checking_boosts")
    cards = candidates(payload.get("card_bonuses", []), "card_bonuses")
    others = candidates(payload.get("other_bonuses", []), "other_bonuses")
    selected_checking = select_highest(checking)
    selected_card = select_highest(cards)
    eligible_others = [item for item in others if item["eligible"]]

    total = base
    if selected_checking:
        total += selected_checking["apy"]
    if selected_card:
        total += selected_card["apy"]
    total += sum((item["apy"] for item in eligible_others), Decimal("0"))

    return {
        "base_apy": f"{base:.6f}",
        "selected_checking_boost": render(selected_checking),
        "selected_card_bonus": render(selected_card),
        "selected_other_bonuses": [render(item) for item in eligible_others],
        "effective_apy": f"{total:.6f}",
        "excluded_checking_candidates": [render(item) for item in checking if not item["eligible"]],
        "excluded_card_candidates": [render(item) for item in cards if not item["eligible"]],
        "assumptions": [
            "Only the highest eligible checking boost is included.",
            "Only the highest eligible credit-card bonus is included.",
            "Each eligible other bonus is additive only when separately documented.",
        ],
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
