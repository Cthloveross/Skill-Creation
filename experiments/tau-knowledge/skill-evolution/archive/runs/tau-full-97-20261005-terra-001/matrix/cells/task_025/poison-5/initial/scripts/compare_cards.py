#!/usr/bin/env python3
"""Compare documented card terms supplied as JSON; reads stdin and writes JSON."""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return str(Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP))


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")
    return result


def parse_day(value, field):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(f"{field} must begin with a valid YYYY-MM-DD date")


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def active_promotion(promotion, today):
    if not promotion.get("eligible", False):
        return False
    start = promotion.get("start")
    end = promotion.get("end")
    if not start or not end:
        return False
    return parse_day(start, "promotion.start") <= today <= parse_day(end, "promotion.end")


def evaluate(product, purchase, today):
    name = product.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each product requires a nonempty name")
    rates = product.get("reward_rates")
    if not isinstance(rates, dict) or "default" not in rates:
        raise ValueError(f"{name}: reward_rates must include default")

    category = normalized(purchase.get("category"))
    merchant = normalized(purchase.get("merchant"))
    rate_source = "default"
    raw_rate = rates.get(category, rates["default"])
    rate = decimal_value(raw_rate, f"{name} reward rate")
    exclusion_reason = None
    for exclusion in product.get("exclusions", []) or []:
        if merchant and normalized(exclusion.get("merchant")) == merchant:
            rate = decimal_value(exclusion.get("rate"), f"{name} exclusion rate")
            rate_source = "merchant exclusion"
            exclusion_reason = exclusion.get("reason") or "documented merchant exclusion"
            break
    if rate < 0:
        raise ValueError(f"{name}: reward rate cannot be negative")

    labels = []
    multiplier = Decimal("1")
    first_year_fee = decimal_value(product.get("annual_fee", 0), f"{name} annual_fee")
    if first_year_fee < 0:
        raise ValueError(f"{name}: annual_fee cannot be negative")
    for promo in product.get("promotions", []) or []:
        if not active_promotion(promo, today):
            continue
        kind = promo.get("kind")
        label = promo.get("label") or kind or "promotion"
        if kind == "reward_multiplier":
            candidate = decimal_value(promo.get("multiplier"), f"{name} promotion multiplier")
            if candidate < 0:
                raise ValueError(f"{name}: promotion multiplier cannot be negative")
            multiplier *= candidate
            labels.append(label)
        elif kind == "first_year_fee":
            candidate = decimal_value(promo.get("fee"), f"{name} promotion fee")
            if candidate < 0:
                raise ValueError(f"{name}: promotion fee cannot be negative")
            first_year_fee = candidate
            labels.append(label)

    amount = decimal_value(purchase["amount"], "purchase.amount")
    effective_rate = rate * multiplier
    cash_back = amount * effective_rate / Decimal("100")
    net = cash_back - first_year_fee

    limit_max_raw = product.get("limit_max")
    limit_max = None if limit_max_raw is None else decimal_value(limit_max_raw, f"{name} limit_max")
    single_required = bool(purchase.get("single_payment_required", True))
    if not single_required:
        limit_status = "not_screened"
        limit_note = "Purchase was not marked as requiring one single charge."
        feasible = True
    elif limit_max is None:
        limit_status = "unknown"
        limit_note = "No documented maximum limit was supplied; single-charge capacity cannot be assessed."
        feasible = False
    elif limit_max < amount:
        limit_status = "insufficient_documented_maximum"
        limit_note = "The documented maximum limit is below the planned single charge."
        feasible = False
    else:
        limit_status = "potentially_supported"
        limit_note = "The documented maximum can accommodate the amount, but approval, assigned line, available credit, and authorization remain unconfirmed."
        feasible = True

    point_value = decimal_value(product.get("point_value", "0.01"), f"{name} point_value")
    stored_points = None
    if product.get("stored_as_points", False):
        if point_value <= 0:
            raise ValueError(f"{name}: point_value must be greater than zero")
        stored_points = str((cash_back / point_value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return {
        "name": name,
        "category_used": category or None,
        "rate_source": rate_source,
        "base_rate_percent": str(rate),
        "effective_rate_percent": str(effective_rate),
        "cash_back_value": money(cash_back),
        "first_year_annual_fee": money(first_year_fee),
        "net_first_year_value": money(net),
        "active_promotions": labels,
        "merchant_exclusion_reason": exclusion_reason,
        "rewards_conditional_on_merchant_category": not bool(purchase.get("merchant_category_confirmed", False)),
        "limit_status": limit_status,
        "limit_note": limit_note,
        "potentially_feasible_for_single_charge": feasible,
        "estimated_stored_points": stored_points,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    purchase = payload.get("purchase")
    if not isinstance(purchase, dict):
        raise ValueError("purchase object is required")
    amount = decimal_value(purchase.get("amount"), "purchase.amount")
    if amount <= 0:
        raise ValueError("purchase.amount must be greater than zero")
    today = parse_day(payload.get("as_of"), "as_of")
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty array")
    results = [evaluate(product, purchase, today) for product in products]
    results.sort(key=lambda item: (
        not item["potentially_feasible_for_single_charge"],
        -Decimal(item["net_first_year_value"]),
        item["name"].casefold(),
    ))
    return {
        "as_of": today.isoformat(),
        "purchase_amount": money(amount),
        "ranked_products": results,
        "disclaimer": "Estimates use supplied product terms. Merchant coding, offer eligibility, underwriting, approved credit line, available credit, and authorization are not established by this calculation.",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
