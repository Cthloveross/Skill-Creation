#!/usr/bin/env python3
"""Rank compatible checking/savings/card APY combinations.

Reads JSON from stdin and writes JSON to stdout. See SKILL.md for schema.
All APY and boost values are percentage points, represented as strings or numbers.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")


def dec(value, field, errors, default=None):
    if value is None:
        if default is not None:
            return default
        errors.append("missing " + field)
        return None
    try:
        answer = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append("invalid decimal for " + field)
        return None
    return answer


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def main(data):
    errors = []
    principal = dec(data.get("principal"), "principal", errors)
    required_days = dec(data.get("required_early_direct_deposit_days", 0),
                        "required_early_direct_deposit_days", errors, ZERO)
    if principal is not None and principal < ZERO:
        errors.append("principal must not be negative")
    if required_days is not None and required_days < ZERO:
        errors.append("required_early_direct_deposit_days must not be negative")
    if errors:
        return {"ranked_options": [], "exclusions": [], "errors": errors}

    savings_list = data.get("savings", [])
    checking_list = data.get("checking", [])
    card_list = data.get("credit_cards", [])
    if not isinstance(savings_list, list) or not isinstance(checking_list, list) or not isinstance(card_list, list):
        return {"ranked_options": [], "exclusions": [],
                "errors": ["savings, checking, and credit_cards must be arrays"]}

    exclusions = []
    eligible_checking = []
    for c in checking_list:
        name = c.get("name")
        days = dec(c.get("early_direct_deposit_days"), "checking early_direct_deposit_days", errors)
        boosts = c.get("boosts", {})
        if not name or not isinstance(boosts, dict) or days is None:
            exclusions.append({"checking": name or "<unnamed>", "reason": "invalid checking candidate"})
        elif days < required_days:
            exclusions.append({"checking": name, "reason": "does not meet required early direct-deposit days"})
        else:
            eligible_checking.append(c)

    results = []
    for s in savings_list:
        name = s.get("name")
        base = dec(s.get("base_apy"), "savings base_apy", errors)
        opening = dec(s.get("opening_min", 0), "savings opening_min", errors, ZERO)
        ongoing = dec(s.get("ongoing_min", 0), "savings ongoing_min", errors, ZERO)
        rate_min = dec(s.get("min_balance_for_rate", 0), "savings min_balance_for_rate", errors, ZERO)
        rate_max = dec(s.get("max_balance_for_rate"), "savings max_balance_for_rate", errors, None) if "max_balance_for_rate" in s else None
        if not name or base is None or opening is None or ongoing is None or rate_min is None:
            exclusions.append({"savings": name or "<unnamed>", "reason": "invalid savings candidate"})
            continue
        if principal < opening:
            exclusions.append({"savings": name, "reason": "principal is below opening minimum"})
            continue
        if principal < ongoing:
            exclusions.append({"savings": name, "reason": "principal is below ongoing minimum"})
            continue
        if principal < rate_min:
            exclusions.append({"savings": name, "reason": "principal does not meet this APY tier minimum"})
            continue
        if rate_max is not None and principal > rate_max:
            exclusions.append({"savings": name, "reason": "principal exceeds this APY tier maximum"})
            continue

        matching_checks = []
        for c in eligible_checking:
            raw_boost = c.get("boosts", {}).get(name)
            if raw_boost is None:
                continue
            boost = dec(raw_boost, "checking boost", errors)
            if boost is not None:
                matching_checks.append((boost, c.get("name")))
        if not matching_checks:
            exclusions.append({"savings": name, "reason": "no documented compatible checking candidate meets required features"})
            continue
        checking_boost, checking_name = max(matching_checks, key=lambda x: (x[0], x[1]))

        matching_cards = [(ZERO, None, None)]
        for card in card_list:
            raw_bonus = card.get("bonuses", {}).get(name) if isinstance(card.get("bonuses", {}), dict) else None
            if raw_bonus is None:
                continue
            bonus = dec(raw_bonus, "credit-card bonus", errors)
            if bonus is not None:
                matching_cards.append((bonus, card.get("name"), card.get("conditional_note")))
        card_bonus, card_name, conditional_note = max(matching_cards, key=lambda x: (x[0], x[1] or ""))
        effective = base + checking_boost + card_bonus
        interest = principal * effective / HUNDRED
        results.append({
            "savings": name,
            "checking": checking_name,
            "credit_card": card_name,
            "credit_card_condition": conditional_note,
            "base_apy_percent": str(base),
            "checking_boost_percent": str(checking_boost),
            "credit_card_bonus_percent": str(card_bonus),
            "effective_apy_percent": str(effective),
            "one_year_interest": money(interest),
            "one_year_ending_balance": money(principal + interest)
        })

    results.sort(key=lambda x: (Decimal(x["effective_apy_percent"]), x["savings"], x["checking"]), reverse=True)
    return {"ranked_options": results, "exclusions": exclusions, "errors": errors}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ranked_options": [], "exclusions": [], "errors": [str(exc)]}, sort_keys=True))
        sys.exit(1)
