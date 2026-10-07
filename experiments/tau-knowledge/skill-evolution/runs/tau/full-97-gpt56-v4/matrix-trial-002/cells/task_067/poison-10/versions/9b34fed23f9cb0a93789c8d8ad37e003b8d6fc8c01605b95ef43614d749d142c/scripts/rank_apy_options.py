#!/usr/bin/env python3
"""Rank documented savings APY combinations from JSON stdin.

Input schema:
{
  "balance": number,
  "savings": [{"name": str, "base_apy": number,
               "opening_deposit": number, "minimum_balance": number,
               "eligible": bool (optional, defaults true)}],
  "checking_boosts": [{"checking": str, "savings": str,
                        "apy_boost": number, "eligible": bool}],
  "card_bonuses": [{"card": str, "savings": str, "apy_bonus": number,
                    "eligible": bool, "held": bool (optional)}],
  "require_held_card": bool (optional, default true)
}

Output schema:
{"ranked_options": [...], "excluded": [...], "errors": [...]}
APYs are percentage points, not fractional rates. The helper applies the general
selection policy: highest eligible linked-checking boost plus highest eligible
card bonus for each eligible savings product. It is not an eligibility engine.
"""
import json
import sys


def numeric(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return None
    if value < 0:
        errors.append(f"{field} must not be negative")
        return None
    return float(value)


def main(data):
    errors, excluded, ranked = [], [], []
    if not isinstance(data, dict):
        return {"ranked_options": [], "excluded": [], "errors": ["input must be an object"]}
    balance = numeric(data.get("balance"), "balance", errors)
    savings = data.get("savings")
    boosts = data.get("checking_boosts", [])
    cards = data.get("card_bonuses", [])
    held_only = data.get("require_held_card", True)
    if not isinstance(savings, list): errors.append("savings must be a list")
    if not isinstance(boosts, list): errors.append("checking_boosts must be a list")
    if not isinstance(cards, list): errors.append("card_bonuses must be a list")
    if not isinstance(held_only, bool): errors.append("require_held_card must be boolean")
    if errors:
        return {"ranked_options": [], "excluded": [], "errors": errors}

    for i, item in enumerate(savings):
        where = f"savings[{i}]"
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            errors.append(f"{where}.name must be a nonempty string")
            continue
        base = numeric(item.get("base_apy"), f"{where}.base_apy", errors)
        opening = numeric(item.get("opening_deposit", 0), f"{where}.opening_deposit", errors)
        minimum = numeric(item.get("minimum_balance", 0), f"{where}.minimum_balance", errors)
        eligible = item.get("eligible", True)
        if not isinstance(eligible, bool):
            errors.append(f"{where}.eligible must be boolean")
            continue
        if None in (base, opening, minimum):
            continue
        reasons = []
        if not eligible: reasons.append("savings product is not confirmed eligible")
        if balance < opening: reasons.append("balance is below required opening deposit")
        if balance < minimum: reasons.append("balance is below required minimum balance")
        if reasons:
            excluded.append({"savings": item["name"], "reasons": reasons})
            continue

        applicable_boosts = []
        for j, b in enumerate(boosts):
            if not isinstance(b, dict):
                errors.append(f"checking_boosts[{j}] must be an object")
                continue
            if b.get("savings") != item["name"] or b.get("eligible") is not True:
                continue
            val = numeric(b.get("apy_boost"), f"checking_boosts[{j}].apy_boost", errors)
            if val is not None and isinstance(b.get("checking"), str):
                applicable_boosts.append((val, b["checking"]))
        check_boost, check_name = max(applicable_boosts, default=(0.0, None), key=lambda x: x[0])

        applicable_cards = []
        for j, c in enumerate(cards):
            if not isinstance(c, dict):
                errors.append(f"card_bonuses[{j}] must be an object")
                continue
            if c.get("savings") != item["name"] or c.get("eligible") is not True:
                continue
            if held_only and c.get("held") is not True:
                continue
            val = numeric(c.get("apy_bonus"), f"card_bonuses[{j}].apy_bonus", errors)
            if val is not None and isinstance(c.get("card"), str):
                applicable_cards.append((val, c["card"]))
        card_boost, card_name = max(applicable_cards, default=(0.0, None), key=lambda x: x[0])
        ranked.append({
            "savings": item["name"], "effective_apy": round(base + check_boost + card_boost, 6),
            "base_apy": base,
            "selected_checking": check_name,
            "checking_boost": check_boost,
            "selected_card": card_name,
            "card_bonus": card_boost,
            "balance": balance,
        })
    ranked.sort(key=lambda x: (-x["effective_apy"], x["savings"], x["selected_checking"] or "", x["selected_card"] or ""))
    return {"ranked_options": ranked, "excluded": excluded, "errors": errors}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ranked_options": [], "excluded": [], "errors": [f"invalid JSON: {exc.msg}"]}))
    except Exception as exc:
        print(json.dumps({"ranked_options": [], "excluded": [], "errors": [f"unexpected error: {type(exc).__name__}"]}))
