#!/usr/bin/env python3
"""Rank savings-account/new-credit-card pairings from JSON stdin.

This utility calculates only a stable-balance, one-year interest-minus-known-fees
comparison. APY figures and bonuses are supplied by the caller as percentage
points. It deliberately does not estimate card rewards, spending promotions,
or application approval.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def decimal_value(value, path, errors, default=None):
    if value is None:
        if default is not None:
            return default
        errors.append(f"{path} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{path} must be numeric, not boolean")
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{path} must be numeric")
        return None
    if not number.is_finite():
        errors.append(f"{path} must be finite")
        return None
    return number


def nonnegative(value, path, errors, default=ZERO):
    number = decimal_value(value, path, errors, default)
    if number is not None and number < ZERO:
        errors.append(f"{path} must not be negative")
        return None
    return number


def eligibility(value):
    """Return eligible, ineligible, or conditional from flexible public input."""
    if value is False or value == "ineligible":
        return "ineligible"
    if value in (None, True, "eligible", "confirmed"):
        return "eligible"
    return "conditional"


def tier_apy(option, balance, index, errors):
    tiers = option.get("tiers")
    if tiers is None:
        return nonnegative(option.get("base_apy"), f"savings_options[{index}].base_apy", errors)
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"savings_options[{index}].tiers must be a nonempty array")
        return None
    qualifying = []
    for tier_index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            errors.append(f"savings_options[{index}].tiers[{tier_index}] must be an object")
            continue
        minimum = nonnegative(tier.get("minimum_balance"),
                              f"savings_options[{index}].tiers[{tier_index}].minimum_balance", errors)
        apy = nonnegative(tier.get("apy"), f"savings_options[{index}].tiers[{tier_index}].apy", errors)
        if minimum is not None and apy is not None and minimum <= balance:
            qualifying.append((minimum, apy))
    if not qualifying:
        errors.append(f"savings_options[{index}] has no tier for the supplied balance")
        return None
    return max(qualifying, key=lambda item: item[0])[1]


def card_bonus(savings, card, errors, label):
    mapping = savings.get("card_bonuses", {})
    if mapping is None:
        mapping = {}
    if not isinstance(mapping, dict):
        errors.append(f"{label}.card_bonuses must be an object")
        return None
    raw = mapping.get(card.get("name"))
    if raw is None:
        alternate = card.get("bonus_by_savings", {})
        if alternate is None:
            alternate = {}
        if not isinstance(alternate, dict):
            errors.append(f"card {card.get('name', '<unnamed>')}.bonus_by_savings must be an object")
            return None
        raw = alternate.get(savings.get("name"), ZERO)
    return nonnegative(raw, f"{label}.card bonus for {card.get('name', '<unnamed>')}", errors)


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["input must be a JSON object"]}

    balance = nonnegative(payload.get("balance"), "balance", errors)
    savings_options = payload.get("savings_options")
    cards = payload.get("cards")
    existing_cards = payload.get("existing_cards", [])
    if not isinstance(savings_options, list) or not savings_options:
        errors.append("savings_options must be a nonempty array")
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty array")
    if not isinstance(existing_cards, list):
        errors.append("existing_cards must be an array")
    if errors:
        return {"ok": False, "errors": errors}

    results = []
    excluded = []
    for s_index, savings in enumerate(savings_options):
        if not isinstance(savings, dict) or not isinstance(savings.get("name"), str) or not savings["name"].strip():
            excluded.append({"savings_index": s_index, "reason": "Savings option needs a nonempty name."})
            continue
        local_errors = []
        base_apy = tier_apy(savings, balance, s_index, local_errors)
        opening_min = nonnegative(savings.get("minimum_opening_deposit"),
                                  f"savings_options[{s_index}].minimum_opening_deposit", local_errors, ZERO)
        ongoing_min = nonnegative(savings.get("ongoing_minimum_balance"),
                                  f"savings_options[{s_index}].ongoing_minimum_balance", local_errors, ZERO)
        account_annual_fee = nonnegative(savings.get("annual_fee"),
                                         f"savings_options[{s_index}].annual_fee", local_errors, ZERO)
        monthly_shortfall_fee = nonnegative(savings.get("monthly_fee_if_below_minimum"),
                                            f"savings_options[{s_index}].monthly_fee_if_below_minimum", local_errors, ZERO)
        additive = nonnegative(savings.get("additive_bonus_apy"),
                               f"savings_options[{s_index}].additive_bonus_apy", local_errors, ZERO)
        if local_errors:
            excluded.append({"savings": savings["name"], "reason": "; ".join(local_errors)})
            continue
        if eligibility(savings.get("eligibility")) == "ineligible":
            excluded.append({"savings": savings["name"], "reason": "Savings eligibility is marked ineligible."})
            continue
        if balance < opening_min:
            excluded.append({"savings": savings["name"], "reason": "Balance is below the minimum opening deposit."})
            continue
        requires_ongoing = savings.get("require_ongoing_minimum", True)
        if requires_ongoing and balance < ongoing_min:
            excluded.append({"savings": savings["name"], "reason": "Balance is below the required ongoing minimum."})
            continue

        for c_index, card in enumerate(cards):
            if not isinstance(card, dict) or not isinstance(card.get("name"), str) or not card["name"].strip():
                excluded.append({"savings": savings["name"], "card_index": c_index,
                                 "reason": "Card option needs a nonempty name."})
                continue
            card_fee = nonnegative(card.get("annual_fee"), f"cards[{c_index}].annual_fee", errors, ZERO)
            if card_fee is None:
                continue
            if eligibility(card.get("eligibility")) == "ineligible":
                excluded.append({"savings": savings["name"], "card": card["name"],
                                 "reason": "Card eligibility is marked ineligible."})
                continue

            held_cards = list(existing_cards) + [card]
            bonuses = []
            invalid_bonus = False
            conditional = eligibility(savings.get("eligibility")) == "conditional" or eligibility(card.get("eligibility")) == "conditional"
            for held in held_cards:
                if not isinstance(held, dict) or not isinstance(held.get("name"), str):
                    errors.append("Every existing_cards item must be an object with a name")
                    invalid_bonus = True
                    break
                if eligibility(held.get("eligibility")) == "ineligible":
                    continue
                bonus = card_bonus(savings, held, errors, f"savings_options[{s_index}]")
                if bonus is None:
                    invalid_bonus = True
                    break
                bonuses.append((bonus, held["name"]))
                if eligibility(held.get("eligibility")) == "conditional":
                    conditional = True
            if invalid_bonus:
                continue
            highest_bonus, source_card = max(bonuses, key=lambda item: item[0]) if bonuses else (ZERO, None)
            shortfall_fees = monthly_shortfall_fee * Decimal("12") if balance < ongoing_min else ZERO
            effective_apy = base_apy + additive + highest_bonus
            gross_interest = money(balance * effective_apy / Decimal("100"))
            known_fees = money(card_fee + account_annual_fee + shortfall_fees)
            net = money(gross_interest - known_fees)
            results.append({
                "savings": savings["name"],
                "card": card["name"],
                "status": "conditional" if conditional else "confirmed",
                "base_apy_percent": str(base_apy),
                "additive_bonus_apy_percent": str(additive),
                "highest_card_bonus_apy_percent": str(highest_bonus),
                "highest_card_bonus_source": source_card,
                "effective_apy_percent": str(effective_apy),
                "gross_one_year_interest_usd": str(gross_interest),
                "known_one_year_fees_usd": str(known_fees),
                "net_one_year_interest_less_fees_usd": str(net),
                "assumptions": [
                    "The supplied balance remains constant for one year.",
                    "Only the highest applicable credit-card APY bonus is used.",
                    "Card rewards, promotional incentives, card interest, and transaction fees are excluded unless represented in the input."
                ]
            })

    if errors:
        return {"ok": False, "errors": errors, "excluded": excluded}
    results.sort(key=lambda item: (-Decimal(item["net_one_year_interest_less_fees_usd"]), item["savings"], item["card"]))
    return {
        "ok": True,
        "ranking_basis": "one-year savings interest at effective APY less known annual and determinable shortfall fees",
        "ranked_pairings": results,
        "excluded": excluded,
        "validation_note": "A confirmed calculation is not account-opening or card-application approval; complete operational eligibility and authorization checks separately."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON input: {exc.msg}"]}))
        sys.exit(0)
    print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True))
