#!/usr/bin/env python3
"""Rank documented savings/card combinations.

Input JSON:
{
  "principal": number|string,
  "savings_products": [optional product objects],
  "credit_cards": [optional card objects],
  "checking_boosts": [optional {"savings_name": str, "apy_boost": number,
                                      "eligibility": "confirmed"|"unknown"|"ineligible"}],
  "relationship_bonuses": {optional savings name: APY bonus}
}

A savings product has name, opening_minimum, ongoing_minimum, tiers
([{minimum_balance, apy}]), annual_non_card_fee (optional), and eligibility
(optional). A card has name, annual_fee, bonuses ({savings name: APY bonus}),
and eligibility (optional). Omitting both product arrays loads the packaged
catalog. Values marked unknown are ranked conditionally; ineligible values are
excluded. Output is one JSON object with ok, errors, warnings, and ranked.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value, field, errors, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric, not boolean")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def status(value):
    if value is True or value == "confirmed":
        return "confirmed"
    if value is False or value == "ineligible":
        return "ineligible"
    return "unknown"


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def percentage(value):
    return format(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), "f")


def load_default_catalog(errors):
    path = Path(__file__).resolve().parent.parent / "references" / "product_catalog.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Could not load packaged catalog: {exc}")
        return {}


def tier_apy(product, principal, errors):
    tiers = product.get("tiers")
    name = product.get("name", "unnamed savings product")
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"{name}: tiers must be a nonempty list")
        return None
    qualifying = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            errors.append(f"{name}: tier {index} must be an object")
            continue
        minimum = decimal_value(tier.get("minimum_balance"), f"{name} tier {index} minimum_balance", errors)
        apy = decimal_value(tier.get("apy"), f"{name} tier {index} apy", errors)
        if minimum is None or apy is None:
            continue
        if minimum < ZERO or apy < ZERO:
            errors.append(f"{name}: tier {index} cannot have a negative value")
            continue
        if principal >= minimum:
            qualifying.append((minimum, apy))
    if not qualifying:
        return None
    return max(qualifying, key=lambda pair: pair[0])[1]


def main(payload):
    errors, warnings, ranked = [], [], []
    principal = decimal_value(payload.get("principal"), "principal", errors)
    if principal is not None and principal <= ZERO:
        errors.append("principal must be greater than zero")
    supplied_savings = payload.get("savings_products")
    supplied_cards = payload.get("credit_cards")
    if (supplied_savings is None) != (supplied_cards is None):
        errors.append("provide both savings_products and credit_cards, or omit both to use the packaged catalog")
    if supplied_savings is None and supplied_cards is None:
        catalog = load_default_catalog(errors)
        savings_products = catalog.get("savings_products", [])
        cards = catalog.get("credit_cards", [])
    else:
        savings_products, cards = supplied_savings, supplied_cards
    if not isinstance(savings_products, list) or not isinstance(cards, list):
        errors.append("savings_products and credit_cards must be arrays")
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "ranked": ranked}

    checking_by_savings = {}
    boosts = payload.get("checking_boosts", [])
    if not isinstance(boosts, list):
        errors.append("checking_boosts must be an array")
        boosts = []
    for index, boost in enumerate(boosts):
        if not isinstance(boost, dict) or not isinstance(boost.get("savings_name"), str):
            errors.append(f"checking_boosts[{index}] must include savings_name")
            continue
        amount = decimal_value(boost.get("apy_boost"), f"checking_boosts[{index}].apy_boost", errors)
        if amount is None or amount < ZERO:
            continue
        eligibility = status(boost.get("eligibility", "confirmed"))
        if eligibility == "ineligible":
            continue
        checking_by_savings.setdefault(boost["savings_name"], []).append((amount, eligibility))

    relationship_bonuses = payload.get("relationship_bonuses", {})
    if not isinstance(relationship_bonuses, dict):
        errors.append("relationship_bonuses must be an object")
        relationship_bonuses = {}
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "ranked": ranked}

    for product in savings_products:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str):
            errors.append("every savings product must be an object with a string name")
            continue
        name = product["name"]
        if status(product.get("eligibility", "confirmed")) == "ineligible":
            warnings.append(f"{name}: excluded because savings eligibility is ineligible")
            continue
        opening = decimal_value(product.get("opening_minimum"), f"{name}.opening_minimum", errors, allow_none=True)
        ongoing = decimal_value(product.get("ongoing_minimum"), f"{name}.ongoing_minimum", errors, allow_none=True)
        if opening is None or ongoing is None:
            warnings.append(f"{name}: excluded because an opening or ongoing minimum is unknown")
            continue
        if opening < ZERO or ongoing < ZERO:
            errors.append(f"{name}: minimum balances cannot be negative")
            continue
        if principal < opening or principal < ongoing:
            warnings.append(f"{name}: excluded because principal does not meet documented minimums")
            continue
        base_apy = tier_apy(product, principal, errors)
        if base_apy is None:
            warnings.append(f"{name}: excluded because no APY tier is met")
            continue
        savings_fee = decimal_value(product.get("annual_non_card_fee", 0), f"{name}.annual_non_card_fee", errors)
        if savings_fee is None or savings_fee < ZERO:
            continue
        matching_boosts = checking_by_savings.get(name, [])
        if matching_boosts:
            checking_bonus, checking_status = max(matching_boosts, key=lambda item: item[0])
        else:
            checking_bonus, checking_status = ZERO, "confirmed"
        relationship_bonus = decimal_value(relationship_bonuses.get(name, 0), f"relationship_bonuses.{name}", errors)
        if relationship_bonus is None or relationship_bonus < ZERO:
            continue

        for card in cards:
            if not isinstance(card, dict) or not isinstance(card.get("name"), str):
                errors.append("every credit card must be an object with a string name")
                continue
            card_name = card["name"]
            card_status = status(card.get("eligibility", "confirmed"))
            if card_status == "ineligible":
                continue
            card_fee = decimal_value(card.get("annual_fee"), f"{card_name}.annual_fee", errors, allow_none=True)
            if card_fee is None:
                warnings.append(f"{card_name}: excluded because annual fee is unknown")
                continue
            if card_fee < ZERO:
                errors.append(f"{card_name}.annual_fee cannot be negative")
                continue
            bonuses = card.get("bonuses", {})
            if not isinstance(bonuses, dict):
                errors.append(f"{card_name}.bonuses must be an object")
                continue
            card_bonus = decimal_value(bonuses.get(name, 0), f"{card_name} bonus for {name}", errors)
            if card_bonus is None or card_bonus < ZERO:
                continue
            effective_apy = base_apy + card_bonus + checking_bonus + relationship_bonus
            interest = principal * effective_apy / Decimal("100")
            fees = card_fee + savings_fee
            candidate_status = "confirmed"
            conditions = []
            if status(product.get("eligibility", "confirmed")) != "confirmed":
                candidate_status = "conditional"
                conditions.append("savings eligibility must be verified")
            if card_status != "confirmed":
                candidate_status = "conditional"
                conditions.append("card eligibility and approval must be verified")
            if checking_status != "confirmed":
                candidate_status = "conditional"
                conditions.append("checking-boost eligibility must be verified")
            ranked.append({
                "savings_account": name,
                "credit_card": card_name,
                "status": candidate_status,
                "conditions": conditions,
                "base_apy_percent": percentage(base_apy),
                "card_bonus_percent": percentage(card_bonus),
                "checking_bonus_percent": percentage(checking_bonus),
                "relationship_bonus_percent": percentage(relationship_bonus),
                "effective_apy_percent": percentage(effective_apy),
                "estimated_one_year_interest": money(interest),
                "annual_card_fee": money(card_fee),
                "other_annual_fees": money(savings_fee),
                "estimated_one_year_net": money(interest - fees)
            })

    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "ranked": []}
    ranked.sort(key=lambda item: Decimal(item["estimated_one_year_net"]), reverse=True)
    if not ranked:
        warnings.append("No feasible card-and-savings combinations could be ranked from the supplied data.")
    return {"ok": True, "errors": [], "warnings": warnings, "ranked": ranked}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": [], "ranked": []}, separators=(",", ":")))
