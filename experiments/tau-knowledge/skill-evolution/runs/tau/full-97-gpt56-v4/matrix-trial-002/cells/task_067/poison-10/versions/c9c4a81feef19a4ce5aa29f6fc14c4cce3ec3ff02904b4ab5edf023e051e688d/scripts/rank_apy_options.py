#!/usr/bin/env python3
"""Rank documented savings APY combinations from a JSON object on stdin.

APY inputs are percentage points. The script is advisory: callers must supply
only documented terms and verified eligibility. It selects at most one highest
checking boost and one highest card bonus for each eligible savings product.
"""
import json
import sys


def number(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return None
    if value < 0:
        errors.append(f"{field} must not be negative")
        return None
    return float(value)


def required_name(item, field, errors):
    value = item.get(field) if isinstance(item, dict) else None
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be a nonempty string")
        return None
    return value


def main(data):
    errors, excluded, ranked = [], [], []
    if not isinstance(data, dict):
        return {"ranked_options": [], "excluded": [], "errors": ["input must be an object"]}

    balance = number(data.get("balance"), "balance", errors)
    savings = data.get("savings")
    boosts = data.get("checking_boosts", [])
    cards = data.get("card_bonuses", [])
    held_only = data.get("require_held_card", True)
    if not isinstance(savings, list):
        errors.append("savings must be a list")
    if not isinstance(boosts, list):
        errors.append("checking_boosts must be a list")
    if not isinstance(cards, list):
        errors.append("card_bonuses must be a list")
    if not isinstance(held_only, bool):
        errors.append("require_held_card must be boolean")
    if errors:
        return {"ranked_options": [], "excluded": [], "errors": errors}

    normalized_boosts = []
    for index, item in enumerate(boosts):
        prefix = f"checking_boosts[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        checking = required_name(item, "checking", errors)
        savings_name = required_name(item, "savings", errors)
        apy = number(item.get("apy_boost"), f"{prefix}.apy_boost", errors)
        eligible = item.get("eligible")
        if not isinstance(eligible, bool):
            errors.append(f"{prefix}.eligible must be boolean")
        elif checking is not None and savings_name is not None and apy is not None:
            normalized_boosts.append((savings_name, apy, checking, eligible))

    normalized_cards = []
    for index, item in enumerate(cards):
        prefix = f"card_bonuses[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        card = required_name(item, "card", errors)
        savings_name = required_name(item, "savings", errors)
        apy = number(item.get("apy_bonus"), f"{prefix}.apy_bonus", errors)
        eligible = item.get("eligible")
        held = item.get("held", False)
        if not isinstance(eligible, bool):
            errors.append(f"{prefix}.eligible must be boolean")
        if not isinstance(held, bool):
            errors.append(f"{prefix}.held must be boolean")
        if card is not None and savings_name is not None and apy is not None and isinstance(eligible, bool) and isinstance(held, bool):
            normalized_cards.append((savings_name, apy, card, eligible, held))

    for index, item in enumerate(savings):
        prefix = f"savings[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = required_name(item, "name", errors)
        base = number(item.get("base_apy"), f"{prefix}.base_apy", errors)
        opening = number(item.get("opening_deposit", 0), f"{prefix}.opening_deposit", errors)
        minimum = number(item.get("minimum_balance", 0), f"{prefix}.minimum_balance", errors)
        eligible = item.get("eligible", True)
        if not isinstance(eligible, bool):
            errors.append(f"{prefix}.eligible must be boolean")
        if name is None or base is None or opening is None or minimum is None or not isinstance(eligible, bool):
            continue

        reasons = []
        if not eligible:
            reasons.append("savings product is not confirmed eligible")
        if balance < opening:
            reasons.append("balance is below required opening deposit")
        if balance < minimum:
            reasons.append("balance is below required minimum balance")
        if reasons:
            excluded.append({"savings": name, "reasons": reasons})
            continue

        matching_boosts = [(apy, checking) for product, apy, checking, ok in normalized_boosts if product == name and ok]
        checking_boost, checking_name = max(matching_boosts, default=(0.0, None), key=lambda pair: (pair[0], pair[1]))
        matching_cards = [
            (apy, card, held)
            for product, apy, card, ok, held in normalized_cards
            if product == name and ok and (held or not held_only)
        ]
        card_bonus, card_name, card_held = max(matching_cards, default=(0.0, None, False), key=lambda item: (item[0], item[1]))
        ranked.append({
            "savings": name,
            "effective_apy": round(base + checking_boost + card_bonus, 6),
            "base_apy": base,
            "selected_checking": checking_name,
            "checking_boost": checking_boost,
            "selected_card": card_name,
            "card_bonus": card_bonus,
            "selected_card_held": card_held if card_name is not None else None,
            "balance": balance,
        })

    ranked.sort(key=lambda item: (-item["effective_apy"], item["savings"], item["selected_checking"] or "", item["selected_card"] or ""))
    return {"ranked_options": ranked, "excluded": excluded, "errors": errors}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ranked_options": [], "excluded": [], "errors": [f"invalid JSON: {exc.msg}"]}))
    except Exception as exc:
        print(json.dumps({"ranked_options": [], "excluded": [], "errors": [f"unexpected error: {type(exc).__name__}"]}))
