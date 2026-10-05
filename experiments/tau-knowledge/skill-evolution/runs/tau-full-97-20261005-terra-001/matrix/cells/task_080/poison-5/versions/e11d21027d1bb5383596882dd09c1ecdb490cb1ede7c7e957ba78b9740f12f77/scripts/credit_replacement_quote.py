#!/usr/bin/env python3
"""Validate documented credit-card replacement shipping quotes.

Input JSON:
  {"cards": [{"card_type": str, "shipping_speed": "standard"|"expedited",
              "fee_acknowledged": bool (optional)}]}
Output JSON:
  {"ok": bool, "quotes": [...], "errors": [...]}

This helper performs no banking actions and does not determine account eligibility.
"""
import json
import sys


TIERS = {
    "bronze rewards card": "entry",
    "bronze rewards": "entry",
    "ecocard": "entry",
    "business bronze rewards card": "entry",
    "business bronze": "entry",
    "silver rewards card": "mid",
    "silver rewards": "mid",
    "business silver rewards card": "mid",
    "business silver": "mid",
    "green rewards card": "mid",
    "green rewards": "mid",
    "silver zoom card": "mid",
    "silver zoom": "mid",
    "gold rewards card": "premium",
    "gold rewards": "premium",
    "business gold rewards card": "premium",
    "business gold": "premium",
    "platinum rewards card": "premium",
    "platinum rewards": "premium",
    "business platinum rewards card": "premium",
    "business platinum": "premium",
    "diamond elite card": "premium",
    "diamond elite": "premium",
}


def normalized(value):
    return " ".join(value.strip().lower().split()) if isinstance(value, str) else ""


def quote_card(card, index):
    if not isinstance(card, dict):
        return None, [f"cards[{index}] must be an object"]

    card_type = card.get("card_type")
    tier = TIERS.get(normalized(card_type))
    if not tier:
        return None, [f"cards[{index}].card_type is not a documented card type"]

    speed = normalized(card.get("shipping_speed"))
    if speed not in {"standard", "expedited"}:
        return None, [f"cards[{index}].shipping_speed must be standard or expedited"]

    if speed == "standard":
        fee = 0.0
        window = "7–10 business days"
    else:
        fee = {"entry": 15.0, "mid": 10.0, "premium": 0.0}[tier]
        window = "2–3 business days"

    errors = []
    if fee > 0 and card.get("fee_acknowledged") is not True:
        errors.append(
            f"cards[{index}] requires explicit fee_acknowledged=true for the ${fee:.2f} expedited fee"
        )

    return {
        "card_type": card_type,
        "tier": tier,
        "shipping_speed": speed,
        "shipping_fee": f"${fee:.2f}",
        "delivery_window": window,
        "fee_acknowledgement_required": fee > 0,
    }, errors


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "quotes": [], "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        print(json.dumps({"ok": False, "quotes": [], "errors": ["input must contain a cards array"]}))
        return

    quotes = []
    errors = []
    if not payload["cards"]:
        errors.append("cards must contain at least one card")

    for index, card in enumerate(payload["cards"]):
        quote, card_errors = quote_card(card, index)
        if quote is not None:
            quotes.append(quote)
        errors.extend(card_errors)

    print(json.dumps({"ok": not errors, "quotes": quotes, "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
