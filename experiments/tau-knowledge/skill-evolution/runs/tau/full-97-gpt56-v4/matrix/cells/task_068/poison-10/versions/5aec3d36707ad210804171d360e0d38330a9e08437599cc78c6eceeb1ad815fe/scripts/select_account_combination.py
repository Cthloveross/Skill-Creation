#!/usr/bin/env python3
"""Select the highest documented feasible savings/checking combination.

Input JSON:
{
  "savings_amount": "25000",
  "savings_products": [
    {"name": "...", "base_apy": "5.5", "minimum_opening_deposit": "0",
     "minimum_ongoing_balance": "10000"}
  ],
  "checking_options": [
    {"name": "...", "early_direct_deposit_days": 1,
     "savings_boosts": {"Savings Account name": "0.75"}}
  ],
  "credit_card_bonuses": [
    {"savings_name": "...", "bonus_apy": "0.25", "eligible": true}
  ]
}

All APY values are percentage points, not fractional rates. A checking option is
considered only when its savings_boosts explicitly names the savings product.
Output JSON has feasible ranked candidates and an optional best candidate. This
helper does not query systems or perform banking actions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a numeric value") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def display(value):
    return format(value.normalize(), "f") if value else "0"


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    amount = number(data.get("savings_amount"), "savings_amount")
    if amount < 0:
        raise ValueError("savings_amount must not be negative")
    products = data.get("savings_products", [])
    checking = data.get("checking_options", [])
    cards = data.get("credit_card_bonuses", [])
    if not all(isinstance(x, list) for x in (products, checking, cards)):
        raise ValueError("savings_products, checking_options, and credit_card_bonuses must be arrays")

    highest_card = {}
    for card in cards:
        if not isinstance(card, dict) or not card.get("eligible", False):
            continue
        name = card.get("savings_name")
        if not isinstance(name, str) or not name:
            raise ValueError("eligible credit card bonus requires savings_name")
        bonus = number(card.get("bonus_apy"), "credit_card_bonuses.bonus_apy")
        highest_card[name] = max(highest_card.get(name, Decimal("0")), bonus)

    candidates, rejected = [], []
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"]:
            raise ValueError("each savings product requires a nonempty name")
        name = product["name"]
        base = number(product.get("base_apy"), f"{name}.base_apy")
        opening = number(product.get("minimum_opening_deposit", 0), f"{name}.minimum_opening_deposit")
        ongoing = number(product.get("minimum_ongoing_balance", 0), f"{name}.minimum_ongoing_balance")
        required = max(opening, ongoing)
        if amount < required:
            rejected.append({"savings_name": name, "reason": "amount_below_required_opening_or_ongoing_balance", "required_amount": display(required)})
            continue
        card_bonus = highest_card.get(name, Decimal("0"))
        # Include a standalone savings candidate and each explicitly eligible pairing.
        options = [(None, Decimal("0"), 0)]
        for check in checking:
            if not isinstance(check, dict):
                raise ValueError("each checking option must be an object")
            boosts = check.get("savings_boosts", {})
            if not isinstance(boosts, dict) or name not in boosts:
                continue
            check_name = check.get("name")
            if not isinstance(check_name, str) or not check_name:
                raise ValueError("checking option with a boost requires a nonempty name")
            boost = number(boosts[name], f"{check_name}.savings_boosts[{name}]")
            days = int(check.get("early_direct_deposit_days", 0))
            if days < 0:
                raise ValueError("early_direct_deposit_days must not be negative")
            options.append((check_name, boost, days))
        for check_name, boost, days in options:
            candidates.append({
                "savings_name": name,
                "checking_name": check_name,
                "base_apy": display(base),
                "checking_boost_apy": display(boost),
                "highest_eligible_card_bonus_apy": display(card_bonus),
                "effective_apy": display(base + boost + card_bonus),
                "required_amount": display(required),
                "early_direct_deposit_days": days,
            })

    candidates.sort(key=lambda x: (Decimal(x["effective_apy"]), x["early_direct_deposit_days"], x["checking_name"] is not None), reverse=True)
    return {"savings_amount": display(amount), "candidates": candidates, "best_candidate": candidates[0] if candidates else None, "rejected": rejected}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
