#!/usr/bin/env python3
"""Calculate documented card-reward scenarios from JSON supplied on stdin.

The program uses only Python's standard library and writes either a result object
or {"error": {"message": ...}} to stdout.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def decimal_value(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal number, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a valid decimal number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return result


def money(value):
    return format(value.quantize(CENT), ".2f")


def normalize(value):
    return " ".join(str(value).casefold().split())


def text_or_none(value, field):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value.strip() or None


def categories_for(merchant):
    confirmed = text_or_none(merchant.get("confirmed_category"), "merchant.confirmed_category")
    if confirmed:
        return [confirmed]
    possible = merchant.get("possible_categories") or []
    if not isinstance(possible, list):
        raise ValueError("merchant.possible_categories must be a list")
    categories = []
    seen = set()
    for item in possible:
        category = text_or_none(item, "merchant.possible_categories item")
        if category and normalize(category) not in seen:
            categories.append(category)
            seen.add(normalize(category))
    return categories or [None]


def limit_assessment(purchase, maximum):
    if maximum is None:
        return {
            "status": "unknown",
            "message": "No documented maximum was supplied; single-charge feasibility is unknown."
        }
    if maximum < purchase:
        return {
            "status": "insufficient_documented_maximum",
            "message": "The documented maximum is below the requested single-charge amount."
        }
    return {
        "status": "potentially_supported",
        "message": (
            "The documented maximum can potentially support this single charge, but approval, "
            "assigned limit, available credit, and authorization remain unknown."
        )
    }


def promotion_values(card, card_name):
    promotions = card.get("promotions") or []
    if not isinstance(promotions, list):
        raise ValueError(f"{card_name}.promotions must be a list")
    guaranteed = Decimal("0")
    conditional = []
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise ValueError(f"{card_name}.promotions entries must be objects")
        name = str(promotion.get("name") or "unnamed promotion")
        credit = decimal_value(promotion.get("statement_credit", "0"),
                               f"{card_name}.{name}.statement_credit")
        conditions = promotion.get("conditions") or []
        if not isinstance(conditions, list):
            raise ValueError(f"{card_name}.{name}.conditions must be a list")
        if promotion.get("eligible") is True:
            guaranteed += credit
        else:
            conditional.append({
                "name": name,
                "statement_credit": money(credit),
                "conditions": [str(item) for item in conditions]
            })
    return guaranteed, conditional


def reward(purchase, rate):
    # At 1%, each dollar produces one point; a point is worth $0.01.
    points = int((purchase * rate).to_integral_value(rounding=ROUND_FLOOR))
    return points, Decimal(points) / HUNDRED


def exclusion_status(named_brand, billing_merchant, exclusions):
    normalized_exclusions = {normalize(item) for item in exclusions}
    if billing_merchant:
        if normalize(billing_merchant) in normalized_exclusions:
            return "confirmed", "The confirmed billing entity matches a documented exclusion."
        return "not_matched", "The confirmed billing entity does not match a supplied exclusion."
    if named_brand and normalize(named_brand) in normalized_exclusions:
        return "possible", (
            "The named brand appears in a documented exclusion, but the billing entity is not "
            "confirmed; show the excluded-rate alternative and confirm the descriptor."
        )
    return "not_known", "No exclusion match can be established from the supplied merchant identity."


def calculate(card, purchase, category, merchant, include_fee):
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each card requires a nonempty name")
    base_rate = decimal_value(card.get("base_rate_percent"), f"{name}.base_rate_percent")
    raw_rates = card.get("category_rates_percent") or {}
    if not isinstance(raw_rates, dict):
        raise ValueError(f"{name}.category_rates_percent must be an object")
    rates = {normalize(key): decimal_value(value, f"{name}.category_rates_percent[{key}]")
             for key, value in raw_rates.items()}
    exclusions = card.get("excluded_merchants") or []
    if not isinstance(exclusions, list) or not all(isinstance(item, str) for item in exclusions):
        raise ValueError(f"{name}.excluded_merchants must be a list of strings")

    eligible = merchant.get("eligible_purchase", True)
    if eligible not in (True, False):
        raise ValueError("merchant.eligible_purchase must be true or false")
    named_brand = text_or_none(merchant.get("named_brand"), "merchant.named_brand")
    billing = text_or_none(merchant.get("billing_merchant"), "merchant.billing_merchant")
    exclusion, exclusion_message = exclusion_status(named_brand, billing, exclusions)

    if not eligible:
        rate, source = Decimal("0"), "known ineligible purchase"
    elif exclusion == "confirmed":
        rate, source = base_rate, "confirmed documented merchant exclusion; base rate applied"
    elif category is not None and normalize(category) in rates:
        rate, source = rates[normalize(category)], f"documented {category} category rate"
    else:
        rate, source = base_rate, "base rate; category is unknown or has no documented bonus"

    points, cash = reward(purchase, rate)
    exclusion_alternative = None
    if eligible and exclusion == "possible" and rate != base_rate:
        alt_points, alt_cash = reward(purchase, base_rate)
        exclusion_alternative = {
            "rate_percent": str(base_rate),
            "reward_points": alt_points,
            "reward_cash_value": money(alt_cash),
            "message": "If the eventual billing entity is the excluded merchant, this base-rate result applies."
        }

    first_year_fee = (decimal_value(card.get("first_year_annual_fee", "0"),
                                    f"{name}.first_year_annual_fee")
                      if include_fee else Decimal("0"))
    standard_fee = decimal_value(card.get("standard_annual_fee", "0"),
                                 f"{name}.standard_annual_fee")
    guaranteed_credit, conditional = promotion_values(card, name)
    minimum = decimal_value(card.get("credit_limit_min"), f"{name}.credit_limit_min", True)
    maximum = decimal_value(card.get("credit_limit_max"), f"{name}.credit_limit_max", True)

    return {
        "card": name,
        "category_scenario": category if category is not None else "unknown",
        "rate_percent": str(rate),
        "rate_source": source,
        "reward_points": points,
        "reward_cash_value": money(cash),
        "merchant_exclusion_status": exclusion,
        "merchant_exclusion_message": exclusion_message,
        "possible_excluded_outcome": exclusion_alternative,
        "first_year_annual_fee_included": money(first_year_fee),
        "standard_annual_fee": money(standard_fee),
        "guaranteed_statement_credit": money(guaranteed_credit),
        "net_first_year_value": money(cash + guaranteed_credit - first_year_fee),
        "conditional_promotions": conditional,
        "credit_limit": {
            "documented_minimum": money(minimum) if minimum is not None else None,
            "documented_maximum": money(maximum) if maximum is not None else None,
            **limit_assessment(purchase, maximum)
        }
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    purchase = decimal_value(payload.get("purchase_amount"), "purchase_amount")
    merchant = payload.get("merchant")
    if not isinstance(merchant, dict):
        raise ValueError("merchant must be an object")
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty list")
    include_fee = payload.get("include_first_year_fee", True)
    if include_fee not in (True, False):
        raise ValueError("include_first_year_fee must be true or false")

    scenarios = []
    for category in categories_for(merchant):
        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("each card must be an object")
            scenarios.append(calculate(card, purchase, category, merchant, include_fee))
    return {
        "purchase_amount": money(purchase),
        "assumptions": {
            "single_transaction": True,
            "points_conversion": "1 point = $0.01 cash back",
            "rounding": "points are floored per transaction",
            "category_status": "confirmed" if merchant.get("confirmed_category") else "unconfirmed"
        },
        "scenarios": scenarios
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": {"message": str(error)}}))
        sys.exit(1)
