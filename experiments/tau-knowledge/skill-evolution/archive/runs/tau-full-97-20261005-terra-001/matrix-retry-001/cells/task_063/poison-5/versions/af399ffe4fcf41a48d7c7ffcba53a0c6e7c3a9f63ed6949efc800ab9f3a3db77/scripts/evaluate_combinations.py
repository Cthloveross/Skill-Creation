#!/usr/bin/env python3
"""Rank documented savings/card combinations from JSON stdin and emit JSON stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def number(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("%s must be numeric" % field)


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def tier_apy(product, deposit):
    tiers = product.get("tiers") or []
    if not tiers:
        if "base_apy" not in product:
            raise ValueError("savings product %r has neither tiers nor base_apy" % product.get("name"))
        return number(product["base_apy"], "base_apy"), None
    usable = []
    for tier in tiers:
        minimum = number(tier.get("minimum_balance"), "tiers.minimum_balance")
        apy = number(tier.get("apy"), "tiers.apy")
        if minimum <= deposit:
            usable.append((minimum, apy))
    if not usable:
        raise ValueError("deposit does not meet any supplied tier for %r" % product.get("name"))
    minimum, apy = max(usable, key=lambda item: item[0])
    return apy, minimum


def highest_card_bonus(cards, savings_name):
    eligible = []
    for card in cards:
        if card.get("eligible") is not True:
            continue
        mappings = card.get("apy_bonus_by_savings") or {}
        if savings_name in mappings:
            eligible.append((number(mappings[savings_name], "card APY bonus"), card.get("name", "Unnamed card"), card))
    if not eligible:
        return ZERO, None, []
    highest = max(item[0] for item in eligible)
    selected = next(item for item in eligible if item[0] == highest)
    return highest, selected[1], [item[1] for item in eligible if item[0] != highest]


def highest_checking_boost(boosts, savings_name):
    matching = []
    for boost in boosts:
        if boost.get("eligible") is True and boost.get("savings_name") == savings_name:
            matching.append((number(boost.get("apy_bonus", 0), "checking APY bonus"), boost.get("checking_name", "Unnamed checking account")))
    if not matching:
        return ZERO, None, []
    highest = max(item[0] for item in matching)
    selected = next(item for item in matching if item[0] == highest)
    return highest, selected[1], [item[1] for item in matching if item[0] != highest]


def evaluate(data):
    deposit = number(data.get("deposit"), "deposit")
    if deposit < ZERO:
        raise ValueError("deposit must not be negative")
    products = data.get("savings_products")
    if not isinstance(products, list) or not products:
        raise ValueError("savings_products must be a nonempty list")
    cards = data.get("credit_cards") or []
    boosts = data.get("checking_boosts") or []
    include_card_fee = bool(data.get("include_card_fee_in_net", False))
    results = []

    for product in products:
        name = product.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each savings product needs a nonempty name")
        opening = number(product.get("opening_deposit"), "opening_deposit")
        ongoing = number(product.get("ongoing_minimum", 0), "ongoing_minimum")
        base_apy, selected_tier_minimum = tier_apy(product, deposit)
        card_bonus, selected_card, unselected_cards = highest_card_bonus(cards, name)
        checking_bonus, selected_checking, unselected_checking = highest_checking_boost(boosts, name)
        relationship = number(product.get("relationship_bonus_apy", 0), "relationship_bonus_apy")
        other_bonus = number(product.get("other_confirmed_bonus_apy", 0), "other_confirmed_bonus_apy")
        effective = base_apy + card_bonus + checking_bonus + relationship + other_bonus
        gross = money(deposit * effective / Decimal("100"))
        warnings = list(product.get("notes") or [])
        feasible = deposit >= opening
        if not feasible:
            warnings.append("Available deposit is below the required opening deposit.")
        if deposit < ongoing:
            warnings.append("Deposit is below the stated ongoing minimum; review the documented consequence or fee.")
        account_fee = ZERO
        if deposit < ongoing and "below_minimum_period_fee" in product:
            account_fee = number(product["below_minimum_period_fee"], "below_minimum_period_fee") * Decimal("12")
        card_fee = ZERO
        if include_card_fee and selected_card is not None:
            chosen = next(c for c in cards if c.get("name") == selected_card)
            card_fee = number(chosen.get("annual_fee", 0), "annual_fee")
        net = money(gross - account_fee - card_fee)
        results.append({
            "savings_account": name,
            "feasible_opening_deposit": feasible,
            "deposit": float(deposit),
            "selected_tier_minimum_balance": float(selected_tier_minimum) if selected_tier_minimum is not None else None,
            "base_or_tier_apy": float(base_apy),
            "selected_credit_card": selected_card,
            "selected_credit_card_apy_bonus": float(card_bonus),
            "unselected_eligible_cards_not_stacked": unselected_cards,
            "selected_checking_account": selected_checking,
            "selected_checking_apy_bonus": float(checking_bonus),
            "unselected_eligible_checking_accounts_not_stacked": unselected_checking,
            "relationship_bonus_apy": float(relationship),
            "other_confirmed_bonus_apy": float(other_bonus),
            "effective_apy": float(effective),
            "estimated_one_year_gross_interest": float(gross),
            "known_annual_account_fees_in_estimate": float(account_fee),
            "included_card_annual_fee_in_net_estimate": float(card_fee),
            "estimated_one_year_net_after_known_fees": float(net),
            "warnings": warnings
        })
    results.sort(key=lambda row: (row["feasible_opening_deposit"], row["estimated_one_year_gross_interest"], row["effective_apy"]), reverse=True)
    feasible = [row for row in results if row["feasible_opening_deposit"]]
    return {"ranked_options": results, "best_option": feasible[0] if feasible else None}


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(data), indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
