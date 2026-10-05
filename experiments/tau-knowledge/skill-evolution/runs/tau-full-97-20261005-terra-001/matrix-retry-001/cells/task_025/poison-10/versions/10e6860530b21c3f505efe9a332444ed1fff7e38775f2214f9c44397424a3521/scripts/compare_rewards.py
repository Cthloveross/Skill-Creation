#!/usr/bin/env python3
"""Calculate documented card-reward scenarios.

Reads the JSON object described in SKILL.md from stdin and writes a JSON object
on stdout. Uses only the Python standard library.
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
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a valid decimal number") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return number


def money(value):
    return format(value.quantize(CENT), ".2f")


def normalize(value):
    return " ".join(str(value).casefold().split())


def categories_for(merchant):
    confirmed = merchant.get("confirmed_category")
    if confirmed is not None and str(confirmed).strip():
        return [str(confirmed)]
    possible = merchant.get("possible_categories") or []
    if not isinstance(possible, list):
        raise ValueError("merchant.possible_categories must be a list")
    result = []
    for category in possible:
        if category is None or not str(category).strip():
            continue
        text = str(category)
        if text not in result:
            result.append(text)
    return result or [None]


def limit_assessment(purchase, minimum, maximum):
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
            "The documented maximum can potentially support this single charge, "
            "but approval, assigned limit, available credit, and authorization remain unknown."
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
        credit = decimal_value(
            promotion.get("statement_credit", "0"),
            f"{card_name}.{name}.statement_credit"
        )
        conditions = promotion.get("conditions") or []
        if not isinstance(conditions, list):
            raise ValueError(f"{card_name}.{name}.conditions must be a list")
        if promotion.get("eligible") is True:
            guaranteed += credit
        else:
            conditional.append({
                "name": name,
                "statement_credit": money(credit),
                "conditions": [str(condition) for condition in conditions]
            })
    return guaranteed, conditional


def calculate(card, purchase, category, merchant, include_fee):
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each card requires a nonempty name")

    base_rate = decimal_value(card.get("base_rate_percent"), f"{name}.base_rate_percent")
    raw_rates = card.get("category_rates_percent") or {}
    if not isinstance(raw_rates, dict):
        raise ValueError(f"{name}.category_rates_percent must be an object")
    rates = {
        normalize(key): decimal_value(value, f"{name}.category_rates_percent[{key}]")
        for key, value in raw_rates.items()
    }

    billed_merchant = merchant.get("billing_merchant")
    exclusions = card.get("excluded_merchants") or []
    if not isinstance(exclusions, list):
        raise ValueError(f"{name}.excluded_merchants must be a list")
    exclusion_applied = bool(billed_merchant) and normalize(billed_merchant) in {
        normalize(item) for item in exclusions
    }

    eligible_purchase = merchant.get("eligible_purchase", True)
    if eligible_purchase not in (True, False):
        raise ValueError("merchant.eligible_purchase must be true or false")
    if not eligible_purchase:
        rate = Decimal("0")
        rate_source = "known ineligible purchase"
    elif exclusion_applied:
        rate = base_rate
        rate_source = "documented merchant-specific exclusion; base rate applied"
    elif category is not None and normalize(category) in rates:
        rate = rates[normalize(category)]
        rate_source = f"documented {category} category rate"
    else:
        rate = base_rate
        rate_source = "base rate; category is unknown or has no documented bonus"

    # A 1% reward on $1 is one point. Points are floored separately for this charge.
    points = int((purchase * rate).to_integral_value(rounding=ROUND_FLOOR))
    reward_cash = Decimal(points) / HUNDRED
    first_year_fee = decimal_value(
        card.get("first_year_annual_fee", "0"), f"{name}.first_year_annual_fee"
    ) if include_fee else Decimal("0")
    standard_fee = decimal_value(
        card.get("standard_annual_fee", "0"), f"{name}.standard_annual_fee"
    )
    guaranteed_credit, conditional_promotions = promotion_values(card, name)

    minimum = decimal_value(card.get("credit_limit_min"), f"{name}.credit_limit_min", True)
    maximum = decimal_value(card.get("credit_limit_max"), f"{name}.credit_limit_max", True)

    return {
        "card": name,
        "category_scenario": category if category is not None else "unknown",
        "rate_percent": str(rate),
        "rate_source": rate_source,
        "merchant_exclusion_applied": exclusion_applied,
        "reward_points": points,
        "reward_cash_value": money(reward_cash),
        "first_year_annual_fee_included": money(first_year_fee),
        "standard_annual_fee": money(standard_fee),
        "guaranteed_statement_credit": money(guaranteed_credit),
        "net_first_year_value": money(reward_cash + guaranteed_credit - first_year_fee),
        "conditional_promotions": conditional_promotions,
        "credit_limit": {
            "documented_minimum": money(minimum) if minimum is not None else None,
            "documented_maximum": money(maximum) if maximum is not None else None,
            **limit_assessment(purchase, minimum, maximum)
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
