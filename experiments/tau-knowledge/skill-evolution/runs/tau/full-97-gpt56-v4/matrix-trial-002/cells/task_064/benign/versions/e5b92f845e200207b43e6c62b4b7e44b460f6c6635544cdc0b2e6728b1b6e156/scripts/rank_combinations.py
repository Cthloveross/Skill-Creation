#!/usr/bin/env python3
"""Rank feasible savings/card combinations from JSON supplied on stdin.

All percentage values are percentage points (for example, 6.35 means 6.35%).
The script is deliberately product-neutral: callers supply current documented terms.
"""
import json
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


def number(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def required(mapping, key, context):
    if key not in mapping:
        raise ValueError(f"{context} is missing required field '{key}'")
    return mapping[key]


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = number(required(payload, "balance", "input"), "balance")
    if balance < 0:
        raise ValueError("balance cannot be negative")
    products = required(payload, "savings_products", "input")
    cards = required(payload, "cards", "input")
    if not isinstance(products, list) or not isinstance(cards, list):
        raise ValueError("savings_products and cards must be arrays")

    checking_boost = number(payload.get("checking_boost_pct", 0), "checking_boost_pct")
    score = payload.get("credit_score")
    score = number(score, "credit_score") if score is not None else None
    subscription = payload.get("subscription")
    warnings = []
    if score is None:
        warnings.append("Credit score was not supplied; score-dependent cards are excluded.")
    if subscription is None:
        warnings.append("Subscription status was not supplied; subscription-required cards are excluded.")

    ranked, excluded = [], []
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("each savings product must be an object")
        pname = str(required(product, "name", "savings product"))
        base = number(required(product, "base_apy_pct", pname), f"{pname}.base_apy_pct")
        opening_min = number(required(product, "opening_minimum", pname), f"{pname}.opening_minimum")
        ongoing_min = number(required(product, "ongoing_minimum", pname), f"{pname}.ongoing_minimum")
        bonuses = required(product, "card_bonuses_pct", pname)
        if not isinstance(bonuses, dict):
            raise ValueError(f"{pname}.card_bonuses_pct must be an object")
        if balance < opening_min or balance < ongoing_min:
            excluded.append({
                "savings_account": pname,
                "reason": "planned balance does not meet required opening and/or ongoing minimum",
                "opening_minimum": float(opening_min),
                "ongoing_minimum": float(ongoing_min),
            })
            continue
        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("each card must be an object")
            cname = str(required(card, "name", "card"))
            if cname not in bonuses:
                continue
            min_score = card.get("minimum_credit_score")
            if min_score is not None:
                min_score = number(min_score, f"{cname}.minimum_credit_score")
                if score is None or score < min_score:
                    excluded.append({"savings_account": pname, "card": cname, "reason": "credit score is missing or below documented minimum"})
                    continue
            if bool(card.get("requires_subscription", False)) and subscription is not True:
                excluded.append({"savings_account": pname, "card": cname, "reason": "required subscription is missing or unconfirmed"})
                continue
            bonus = number(bonuses[cname], f"{pname}.{cname} bonus")
            annual_fee = number(required(card, "annual_fee", cname), f"{cname}.annual_fee")
            effective = base + bonus + checking_boost
            gross = balance * effective / Decimal("100")
            net = gross - annual_fee
            ranked.append({
                "savings_account": pname,
                "card": cname,
                "base_apy_pct": float(base),
                "card_bonus_pct": float(bonus),
                "checking_boost_pct": float(checking_boost),
                "effective_apy_pct": float(effective),
                "estimated_gross_interest": float(money(gross)),
                "annual_card_fee": float(money(annual_fee)),
                "net_annual_return": float(money(net)),
                "opening_minimum": float(opening_min),
                "ongoing_minimum": float(ongoing_min),
            })
    ranked.sort(key=lambda row: (-Decimal(str(row["net_annual_return"])), row["savings_account"], row["card"]))
    return {"ranked": ranked, "excluded": excluded, "input_warnings": warnings}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True, separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
