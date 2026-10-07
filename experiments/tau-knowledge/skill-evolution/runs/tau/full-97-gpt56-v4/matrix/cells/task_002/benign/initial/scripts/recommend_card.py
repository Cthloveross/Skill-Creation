#!/usr/bin/env python3
"""Rank flat-rate personal cash-back cards.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input keys: cards (list), require_flat_everyday_rate (bool, default true),
limit (positive integer, default 3).
"""
import json
import sys


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "invalid_input", "error": "stdin must contain valid JSON", "detail": str(exc)}))
        return

    cards = payload.get("cards")
    if not isinstance(cards, list):
        print(json.dumps({"status": "invalid_input", "error": "cards must be a list"}))
        return
    require_flat = payload.get("require_flat_everyday_rate", True)
    limit = payload.get("limit", 3)
    if not isinstance(require_flat, bool) or not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        print(json.dumps({"status": "invalid_input", "error": "require_flat_everyday_rate must be boolean and limit a positive integer"}))
        return

    qualified = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        rate = card.get("everyday_eligible_purchase_rate_pct")
        if card.get("personal") is not True or card.get("program_type") != "cash_back" or not is_number(rate):
            continue
        if require_flat and card.get("flat_everyday_rate") is not True:
            continue
        qualified.append(card)

    qualified.sort(key=lambda item: (-item["everyday_eligible_purchase_rate_pct"], str(item.get("name", ""))))
    ranked = qualified[:limit]
    if not ranked:
        print(json.dumps({"status": "no_qualifying_card", "recommendation": None, "ranked_cards": []}))
        return

    winner = ranked[0]
    recommendation = {
        "name": winner.get("name"),
        "everyday_eligible_purchase_rate_pct": winner["everyday_eligible_purchase_rate_pct"],
        "annual_fee_usd": winner.get("annual_fee_usd"),
        "redemption_minimum_usd": winner.get("redemption_minimum_usd"),
        "minimum_credit_score": winner.get("minimum_credit_score"),
    }
    print(json.dumps({"status": "ok", "recommendation": recommendation, "ranked_cards": ranked}, ensure_ascii=False))


if __name__ == "__main__":
    main()
