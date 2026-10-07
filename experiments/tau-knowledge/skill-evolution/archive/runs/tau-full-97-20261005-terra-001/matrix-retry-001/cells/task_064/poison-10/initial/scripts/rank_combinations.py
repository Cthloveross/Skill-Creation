#!/usr/bin/env python3
"""Rank savings/card choices from JSON stdin without performing banking actions.

Input schema is documented in SKILL.md. Monetary and percentage values may be JSON
numbers or decimal strings. Output monetary values are decimal strings rounded to cents.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def nonnegative(value, field):
    result = decimal_value(value, field)
    if result < ZERO:
        raise ValueError(f"{field} must not be negative")
    return result


def text_number(value):
    value = value.quantize(CENT, rounding=ROUND_HALF_UP)
    return format(value, "f")


def text_percent(value):
    value = value.normalize()
    return format(value, "f")


def selected_tier(tiers, balance, option_name):
    if not isinstance(tiers, list) or not tiers:
        raise ValueError(f"{option_name}.tiers must be a nonempty list")
    applicable = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"{option_name}.tiers[{index}] must be an object")
        minimum = nonnegative(tier.get("minimum_balance"),
                              f"{option_name}.tiers[{index}].minimum_balance")
        apy = nonnegative(tier.get("apy_percent"),
                          f"{option_name}.tiers[{index}].apy_percent")
        if minimum <= balance:
            applicable.append((minimum, apy))
    if not applicable:
        raise ValueError(f"{option_name} has no APY tier for the supplied balance")
    return max(applicable, key=lambda item: item[0])


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = nonnegative(payload.get("balance"), "balance")
    opening_deposit = nonnegative(payload.get("opening_deposit", balance), "opening_deposit")
    require_card = payload.get("require_card", False)
    if not isinstance(require_card, bool):
        raise ValueError("require_card must be true or false")
    relationship_bonus = nonnegative(payload.get("relationship_bonus_percent", 0),
                                     "relationship_bonus_percent")
    checking_boost = nonnegative(payload.get("checking_boost_percent", 0),
                                 "checking_boost_percent")
    options = payload.get("savings_options")
    if not isinstance(options, list) or not options:
        raise ValueError("savings_options must be a nonempty list")

    ranked = []
    rejected = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"savings_options[{index}] must be an object")
        name = option.get("account_class")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"savings_options[{index}].account_class must be a nonempty string")
        prefix = f"savings_options[{index}]"
        open_min = nonnegative(option.get("opening_minimum", 0), prefix + ".opening_minimum")
        ongoing_min = nonnegative(option.get("ongoing_minimum", 0), prefix + ".ongoing_minimum")
        maintenance = nonnegative(option.get("annual_maintenance_fee", 0),
                                  prefix + ".annual_maintenance_fee")
        failures = []
        if opening_deposit < open_min:
            failures.append("opening_deposit_below_minimum")
        if balance < ongoing_min:
            failures.append("balance_below_ongoing_minimum")
        if failures:
            rejected.append({"account_class": name, "reasons": failures})
            continue
        tier_minimum, base_apy = selected_tier(option.get("tiers"), balance, prefix)
        cards = option.get("card_options", [])
        if not isinstance(cards, list):
            raise ValueError(prefix + ".card_options must be a list")

        # Every row models zero or one card. This explicitly prevents card APY stacking.
        choices = [] if require_card else [(None, ZERO, ZERO)]
        for card_index, card in enumerate(cards):
            if not isinstance(card, dict):
                raise ValueError(f"{prefix}.card_options[{card_index}] must be an object")
            eligible = card.get("eligible", False)
            if not isinstance(eligible, bool):
                raise ValueError(f"{prefix}.card_options[{card_index}].eligible must be true or false")
            if not eligible:
                continue
            card_name = card.get("card_name")
            if not isinstance(card_name, str) or not card_name.strip():
                raise ValueError(f"{prefix}.card_options[{card_index}].card_name must be a nonempty string")
            bonus = nonnegative(card.get("apy_bonus_percent", 0),
                                f"{prefix}.card_options[{card_index}].apy_bonus_percent")
            fee = nonnegative(card.get("annual_fee", 0),
                              f"{prefix}.card_options[{card_index}].annual_fee")
            choices.append((card_name, bonus, fee))

        for card_name, card_bonus, annual_fee in choices:
            total_apy = base_apy + card_bonus + relationship_bonus + checking_boost
            interest = balance * total_apy / Decimal("100")
            net = interest - annual_fee - maintenance
            ranked.append({
                "eligible": True,
                "account_class": name,
                "card_name": card_name,
                "selected_tier_minimum_balance": text_number(tier_minimum),
                "base_apy_percent": text_percent(base_apy),
                "card_apy_bonus_percent": text_percent(card_bonus),
                "relationship_bonus_percent": text_percent(relationship_bonus),
                "checking_boost_percent": text_percent(checking_boost),
                "total_apy_percent": text_percent(total_apy),
                "annual_interest": text_number(interest),
                "annual_card_fee": text_number(annual_fee),
                "annual_maintenance_fee": text_number(maintenance),
                "net_one_year": text_number(net)
            })

    ranked.sort(key=lambda row: (Decimal(row["net_one_year"]), Decimal(row["total_apy_percent"])), reverse=True)
    return {
        "ok": True,
        "assumptions": {
            "stable_balance": text_number(balance),
            "opening_deposit": text_number(opening_deposit),
            "one_year_interest_uses_stated_apy": True,
            "credit_card_bonuses_are_not_stacked": True,
            "require_card": require_card
        },
        "ranked_combinations": ranked,
        "rejected_savings_options": rejected,
        "best_combination": ranked[0] if ranked else None
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        result = main(data)
    except (ValueError, json.JSONDecodeError) as error:
        result = {"ok": False, "error": str(error)}
    print(json.dumps(result, separators=(",", ":")))
