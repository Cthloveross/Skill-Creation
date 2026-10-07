#!/usr/bin/env python3
"""Return the highest documented flat everyday cash-back card as JSON."""
import json
import sys
from decimal import Decimal

CARDS = [
    {
        "card": "Platinum Rewards Card",
        "all_eligible_purchase_rate_percent": "10.0",
        "annual_fee_usd": "200.00",
        "applies_to": "all eligible posted point-of-sale and online purchases",
    },
    {
        "card": "Diamond Elite Card",
        "all_eligible_purchase_rate_percent": "5.0",
        "annual_fee_usd": None,
        "applies_to": "all eligible purchases",
    },
    {
        "card": "Gold Rewards Card",
        "all_eligible_purchase_rate_percent": "2.5",
        "annual_fee_usd": "0.00",
        "applies_to": "all purchases",
    },
    {
        "card": "Bronze Rewards Card",
        "all_eligible_purchase_rate_percent": "1.0",
        "annual_fee_usd": "0.00",
        "applies_to": "eligible everyday purchases",
    },
]


def error(message):
    return {"status": "error", "error": message}


def main():
    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        print(json.dumps(error("invalid_json_input")))
        return
    if not isinstance(request, dict):
        print(json.dumps(error("input_must_be_an_object")))
        return
    request_type = request.get("request_type", "highest_everyday_cash_back")
    if request_type != "highest_everyday_cash_back":
        print(json.dumps(error("unsupported_request_type")))
        return
    if not CARDS:
        print(json.dumps(error("no_comparable_card_terms")))
        return

    best = max(CARDS, key=lambda item: Decimal(item["all_eligible_purchase_rate_percent"]))
    result = {
        "status": "ok",
        "recommendation": {
            "card": best["card"],
            "cash_back_rate_percent": float(best["all_eligible_purchase_rate_percent"]),
            "annual_fee_usd": (float(best["annual_fee_usd"])
                               if best["annual_fee_usd"] is not None else None),
            "applies_to": best["applies_to"],
            "reason": "It has the highest documented flat cash-back rate among cards whose rate applies to everyday eligible purchases.",
        },
        "comparison_scope": (
            "Compared documented flat rates on all/eligible purchases only; "
            "excluded the Silver Rewards Card's travel-and-software-only rate."
        ),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
