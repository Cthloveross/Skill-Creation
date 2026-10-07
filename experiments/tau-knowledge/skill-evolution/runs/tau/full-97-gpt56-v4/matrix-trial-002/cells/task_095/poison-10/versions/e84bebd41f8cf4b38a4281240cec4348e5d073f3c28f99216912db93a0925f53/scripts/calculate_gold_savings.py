#!/usr/bin/env python3
"""Select non-stacking Gold Savings APY components and calculate a constant-balance cycle.

Reads one JSON object from stdin and emits one JSON object to stdout. See SKILL.md for
schema. Values are Decimal-safe strings or numbers; unsupported account types fail closed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40

CARD_BONUSES = {
    "Bronze Rewards Card": Decimal("0.15"),
    "Silver Rewards Card": Decimal("0.2"),
    "Gold Rewards Card": Decimal("0.025"),
    "Platinum Rewards Card": Decimal("0.15"),
    "Diamond Elite Card": Decimal("0.3"),
    "EcoCard": Decimal("0.6"),
    "Green Rewards Card": Decimal("0.35"),
    "Crypto-Cash Back Card": Decimal("0"),
}
CHECKING_BOOSTS = {
    "Green Account": Decimal("0.75"),
    "Purple Account": Decimal("0.1"),
}
CENT = Decimal("0.01")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def checked_list(data, field, supported):
    values = data.get(field, [])
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        raise ValueError(f"{field} must be an array of strings")
    unknown = sorted(set(values) - set(supported))
    if unknown:
        raise ValueError(f"unsupported {field}: {', '.join(unknown)}")
    return values


def choose_highest(names, rates):
    # Sorting makes tied selected names deterministic and keeps every active candidate visible.
    candidates = [{"account_type": name, "apy_bonus": str(rates[name])} for name in sorted(set(names))]
    if not candidates:
        return None, Decimal("0"), candidates
    highest = max(rates[name] for name in names)
    selected = sorted(name for name in set(names) if rates[name] == highest)
    return selected, highest, candidates


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    base = decimal_value(data.get("base_apy", "5.5"), "base_apy")
    if base < 0:
        raise ValueError("base_apy must not be negative")
    cards = checked_list(data, "active_card_types", CARD_BONUSES)
    checking = checked_list(data, "active_checking_types", CHECKING_BOOSTS)
    relationship_flag = data.get("gold_rewards_relationship_bonus", False)
    if not isinstance(relationship_flag, bool):
        raise ValueError("gold_rewards_relationship_bonus must be boolean")

    selected_cards, card_bonus, card_candidates = choose_highest(cards, CARD_BONUSES)
    selected_checking, checking_bonus, checking_candidates = choose_highest(checking, CHECKING_BOOSTS)
    relationship_bonus = Decimal("0.025") if relationship_flag else Decimal("0")
    expected_apy = base + card_bonus + checking_bonus + relationship_bonus

    result = {
        "base_apy": str(base),
        "credit_card_candidates": card_candidates,
        "selected_highest_credit_card_types": selected_cards,
        "selected_credit_card_bonus": str(card_bonus),
        "checking_candidates": checking_candidates,
        "selected_highest_checking_types": selected_checking,
        "selected_checking_bonus": str(checking_bonus),
        "relationship_bonus": str(relationship_bonus),
        "expected_apy": str(expected_apy),
    }

    has_principal = "principal" in data
    has_days = "days" in data
    if has_principal != has_days:
        raise ValueError("principal and days must be supplied together")
    if has_principal:
        principal = decimal_value(data["principal"], "principal")
        days = data["days"]
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("days must be a positive integer")
        if principal < 0:
            raise ValueError("principal must not be negative")
        daily_rate = expected_apy / Decimal("100") / Decimal("365")
        interest = principal * ((Decimal("1") + daily_rate) ** days - Decimal("1"))
        result.update({
            "principal": str(principal),
            "days": days,
            "expected_interest_unrounded": str(interest),
            "expected_interest_cents": str(interest.quantize(CENT, rounding=ROUND_HALF_UP)),
        })
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
