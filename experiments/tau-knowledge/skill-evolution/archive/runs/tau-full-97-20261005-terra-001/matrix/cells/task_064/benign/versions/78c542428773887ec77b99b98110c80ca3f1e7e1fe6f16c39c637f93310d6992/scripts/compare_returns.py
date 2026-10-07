#!/usr/bin/env python3
"""Rank documented savings/card choices from JSON stdin; writes JSON to stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def dec(value, field, errors, nonnegative=True):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric")
        return None
    if not number.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if nonnegative and number < ZERO:
        errors.append(f"{field} must be nonnegative")
        return None
    return number


def money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def main(data):
    errors = []
    deposit = dec(data.get("deposit_amount"), "deposit_amount", errors)
    products = data.get("savings_products")
    cards = data.get("cards")
    if not isinstance(products, list) or not products:
        errors.append("savings_products must be a nonempty array")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
    if errors:
        return {"status": "error", "errors": errors}

    product_map = {}
    parsed_products = []
    for index, product in enumerate(products):
        prefix = f"savings_products[{index}]"
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        name = product["name"]
        if name in product_map:
            errors.append(f"duplicate savings product name: {name}")
            continue
        base = dec(product.get("base_apy"), f"{prefix}.base_apy", errors)
        opening = dec(product.get("opening_deposit", 0), f"{prefix}.opening_deposit", errors)
        minimum = dec(product.get("minimum_balance", 0), f"{prefix}.minimum_balance", errors)
        monthly = dec(product.get("monthly_maintenance_fee_below_minimum", 0), f"{prefix}.monthly_maintenance_fee_below_minimum", errors)
        if None not in (base, opening, minimum, monthly):
            item = {"name": name, "base": base, "opening": opening, "minimum": minimum, "monthly": monthly}
            product_map[name] = item
            parsed_products.append(item)

    credit_score = data.get("credit_score")
    parsed_score = None
    if credit_score is not None:
        parsed_score = dec(credit_score, "credit_score", errors)

    checking = data.get("checking_boosts", {})
    other = data.get("other_additive_bonuses", {})
    if not isinstance(checking, dict):
        errors.append("checking_boosts must be an object")
        checking = {}
    if not isinstance(other, dict):
        errors.append("other_additive_bonuses must be an object")
        other = {}
    def parse_bonus_map(mapping, label):
        result = {}
        for name, value in mapping.items():
            if name not in product_map:
                errors.append(f"{label} contains unknown savings product: {name}")
                continue
            number = dec(value, f"{label}.{name}", errors)
            if number is not None:
                result[name] = number
        return result
    checking = parse_bonus_map(checking, "checking_boosts")
    other = parse_bonus_map(other, "other_additive_bonuses")

    parsed_cards = []
    for index, card in enumerate(cards):
        prefix = f"cards[{index}]"
        if not isinstance(card, dict) or not isinstance(card.get("name"), str) or not card["name"].strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        fee = dec(card.get("annual_fee"), f"{prefix}.annual_fee", errors)
        threshold_raw = card.get("minimum_credit_score")
        threshold = None if threshold_raw is None else dec(threshold_raw, f"{prefix}.minimum_credit_score", errors)
        bonuses = card.get("apy_bonuses", {})
        if not isinstance(bonuses, dict):
            errors.append(f"{prefix}.apy_bonuses must be an object")
            continue
        parsed_bonuses = parse_bonus_map(bonuses, f"{prefix}.apy_bonuses")
        if fee is not None and (threshold is None or threshold >= ZERO):
            parsed_cards.append({"name": card["name"], "fee": fee, "threshold": threshold, "bonuses": parsed_bonuses})

    if errors:
        return {"status": "error", "errors": errors}

    strict = data.get("strict_maintenance", True)
    if not isinstance(strict, bool):
        return {"status": "error", "errors": ["strict_maintenance must be boolean"]}
    include_no_card = data.get("include_no_card", True)
    if not isinstance(include_no_card, bool):
        return {"status": "error", "errors": ["include_no_card must be boolean"]}
    if include_no_card:
        parsed_cards.append({"name": "No new card", "fee": ZERO, "threshold": None, "bonuses": {}})

    candidates, excluded = [], []
    for product in parsed_products:
        if deposit < product["opening"]:
            excluded.append({"savings_account": product["name"], "reason": "deposit_below_opening_requirement", "required": float(product["opening"])})
            continue
        if strict and deposit < product["minimum"]:
            excluded.append({"savings_account": product["name"], "reason": "deposit_below_ongoing_minimum", "required": float(product["minimum"])})
            continue
        maintenance = ZERO if deposit >= product["minimum"] else product["monthly"] * Decimal("12")
        for card in parsed_cards:
            card_bonus = card["bonuses"].get(product["name"], ZERO)
            rate = product["base"] + card_bonus + checking.get(product["name"], ZERO) + other.get(product["name"], ZERO)
            interest = deposit * rate / Decimal("100")
            net = interest - card["fee"] - maintenance
            if card["threshold"] is not None and parsed_score is None:
                eligibility = "conditional_credit_score"
            elif card["threshold"] is not None and parsed_score < card["threshold"]:
                eligibility = "does_not_meet_stated_credit_minimum"
            else:
                eligibility = "eligible"
            candidates.append({
                "savings_account": product["name"], "card": card["name"],
                "eligibility": eligibility,
                "effective_apy_percent": float(rate),
                "annual_interest": money(interest),
                "annual_card_fee": money(card["fee"]),
                "annual_maintenance_fee_assumed": money(maintenance),
                "net_one_year_return": money(net),
                "components": {"base_apy_percent": float(product["base"]), "card_apy_bonus_percent": float(card_bonus), "checking_apy_boost_percent": float(checking.get(product["name"], ZERO)), "other_additive_apy_bonus_percent": float(other.get(product["name"], ZERO))},
                "requirements": {"opening_deposit": money(product["opening"]), "ongoing_minimum_balance": money(product["minimum"]), "stated_credit_score_minimum": None if card["threshold"] is None else float(card["threshold"])}
            })
    order = {"eligible": 0, "conditional_credit_score": 1, "does_not_meet_stated_credit_minimum": 2}
    candidates.sort(key=lambda row: (order[row["eligibility"]], -row["net_one_year_return"], row["savings_account"], row["card"]))
    return {"status": "ok", "assumptions": {"constant_balance_for_one_year": True, "strict_maintenance": strict, "card_bonuses_are_not_stacked": True, "checking_boosts_are_already_highest_applicable": True}, "candidates": candidates, "excluded": excluded}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"status": "error", "errors": [str(exc)]}, separators=(",", ":")))
