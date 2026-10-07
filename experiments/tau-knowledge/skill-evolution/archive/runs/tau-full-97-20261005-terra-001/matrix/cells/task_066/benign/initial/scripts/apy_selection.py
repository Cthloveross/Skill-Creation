#!/usr/bin/env python3
"""Select non-stacking checking and credit-card APY bonuses from supplied candidates."""
import json
import sys
from decimal import Decimal, InvalidOperation

def dec(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("APY values must be numeric percentages")

def pick(candidates):
    eligible = []
    for candidate in candidates or []:
        if candidate.get("eligible") is True:
            eligible.append((dec(candidate.get("bonus", 0)), candidate.get("name")))
    if not eligible:
        return {"name": None, "bonus": Decimal("0")}
    bonus, name = max(eligible, key=lambda item: item[0])
    return {"name": name, "bonus": bonus}

def text(value):
    return format(value.normalize(), "f") if value else "0"

def main(data):
    base = dec(data["base_apy"])
    checking = pick(data.get("checking_candidates"))
    card = pick(data.get("card_candidates"))
    total = base + checking["bonus"] + card["bonus"]
    return {
        "base_apy": text(base),
        "selected_checking": {"name": checking["name"], "bonus": text(checking["bonus"])},
        "selected_card": {"name": card["name"], "bonus": text(card["bonus"])},
        "total_apy": text(total),
        "policy": "Highest eligible bonus selected independently for checking and credit cards; the two selected categories are additive.",
    }

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"error": "invalid_input", "detail": str(exc)}))
