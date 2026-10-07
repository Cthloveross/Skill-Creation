#!/usr/bin/env python3
"""Calculate conditional reward scenarios for a documented card comparison.

Reads the JSON schema described in SKILL.md from stdin and writes JSON to stdout.
Uses only Python's standard library. Monetary inputs should be strings to avoid
binary floating-point ambiguity.
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
        raise ValueError(f"{field} must be a finite nonnegative number")
    return result


def money(value):
    return format(value.quantize(CENT), ".2f")


def normalized(value):
    return " ".join(str(value).casefold().split())


def limit_assessment(purchase, minimum, maximum):
    if maximum is None:
        return {
            "status": "unknown",
            "message": "No documented maximum credit limit was supplied."
        }
    if maximum < purchase:
        return {
            "status": "insufficient_documented_maximum",
            "message": "The documented maximum is below the requested single-charge amount."
        }
    if minimum is not None and minimum >= purchase:
        message = (
            "The documented range starts at or above the purchase amount, but the "
            "assigned limit and approval remain unknown."
        )
    else:
        message = (
            "The documented maximum can potentially support the purchase, but the "
            "assigned limit and approval remain unknown."
        )
    return {"status": "potentially_supported", "message": message}


def categories_for(merchant):
    confirmed = merchant.get("confirmed_category")
    if confirmed:
        return [str(confirmed)]
    categories = merchant.get("possible_categories") or []
    if not isinstance(categories, list) or not categories:
        return [None]
    unique = []
    for category in categories:
        category = str(category)
        if category not in unique:
            unique.append(category)
    return unique


def calculate_card(card, purchase, category, merchant, include_fee):
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each card requires a nonempty name")
    base_rate = decimal_value(card.get("base_rate_percent"),
                              f"{name}.base_rate_percent")
    category_rates = card.get("category_rates_percent") or {}
    if not isinstance(category_rates, dict):
        raise ValueError(f"{name}.category_rates_percent must be an object")
    normalized_rates = {
        normalized(key): decimal_value(value, f"{name}.category_rates_percent[{key}]")
        for key, value in category_rates.items()
    }
    billed_name = merchant.get("billing_merchant")
    excluded = False
    if billed_name:
        excluded = normalized(billed_name) in {
            normalized(item) for item in (card.get("excluded_merchants") or [])
        }

    eligible_purchase = merchant.get("eligible_purchase", True)
    if eligible_purchase is not True and eligible_purchase is not False:
        raise ValueError("merchant.eligible_purchase must be true or false")

    if not eligible_purchase:
        rate = Decimal("0")
        rate_source = "known ineligible purchase"
    elif excluded:
        rate = base_rate
        rate_source = "merchant-specific exclusion; base rate applied"
    elif category is not None and normalized(category) in normalized_rates:
        rate = normalized_rates[normalized(category)]
        rate_source = f"documented {category} category rate"
    else:
        rate = base_rate
        rate_source = "base rate; category is unknown or has no supplied bonus rate"

    # 1 percent cash back on one dollar is one point. Points are floored per charge.
    points = int((purchase * rate).to_integral_value(rounding=ROUND_FLOOR))
    reward_cash = Decimal(points) / HUNDRED
    fee = decimal_value(card.get("first_year_annual_fee", "0"),
                        f"{name}.first_year_annual_fee") if include_fee else Decimal("0")

    guaranteed_credit = Decimal("0")
    conditional_promotions = []
    promotions = card.get("promotions") or []
    if not isinstance(promotions, list):
        raise ValueError(f"{name}.promotions must be a list")
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise ValueError(f"{name}.promotions entries must be objects")
        promo_name = str(promotion.get("name", "unnamed promotion"))
        credit = decimal_value(promotion.get("statement_credit", "0"),
                               f"{name}.{promo_name}.statement_credit")
        conditions = promotion.get("conditions") or []
        if not isinstance(conditions, list):
            raise ValueError(f"{name}.{promo_name}.conditions must be a list")
        if promotion.get("eligible") is True:
            guaranteed_credit += credit
        else:
            conditional_promotions.append({
                "name": promo_name,
                "statement_credit": money(credit),
                "conditions": [str(item) for item in conditions]
            })

    credit_min = decimal_value(card.get("credit_limit_min"),
                               f"{name}.credit_limit_min", allow_none=True)
    credit_max = decimal_value(card.get("credit_limit_max"),
                               f"{name}.credit_limit_max", allow_none=True)
    net_value = reward_cash + guaranteed_credit - fee

    return {
        "card": name,
        "category_scenario": category if category is not None else "unknown",
        "rate_percent": str(rate),
        "rate_source": rate_source,
        "merchant_exclusion_applied": excluded,
        "reward_points": points,
        "reward_cash_value": money(reward_cash),
        "first_year_annual_fee_included": money(fee),
        "guaranteed_statement_credit": money(guaranteed_credit),
        "net_first_year_value": money(net_value),
        "conditional_promotions": conditional_promotions,
        "credit_limit": {
            "documented_minimum": money(credit_min) if credit_min is not None else None,
            "documented_maximum": money(credit_max) if credit_max is not None else None,
            **limit_assessment(purchase, credit_min, credit_max)
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
    if include_fee is not True and include_fee is not False:
        raise ValueError("include_first_year_fee must be true or false")

    scenarios = []
    for category in categories_for(merchant):
        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("each card must be an object")
            scenarios.append(calculate_card(card, purchase, category, merchant, include_fee))
    return {
        "purchase_amount": money(purchase),
        "assumptions": {
            "single_transaction": True,
            "points_conversion": "1 point = $0.01",
            "rounding": "points are floored for each transaction",
            "category_status": "confirmed" if merchant.get("confirmed_category") else "unconfirmed"
        },
        "scenarios": scenarios
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": {"message": str(error)}}))
        sys.exit(1)
