#!/usr/bin/env python3
"""Rank verified savings-product candidates without performing banking actions.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the input schema. All APY fields are percentages, e.g. "7.0" means 7.0%.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def decimal_value(value, field, product_id, allow_missing=False):
    if value is None and allow_missing:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{product_id}.{field} must be a decimal, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{product_id}.{field} is not a valid decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{product_id}.{field} must be a finite non-negative decimal")
    return result


def bonus_choice(items, field, product_id):
    if items is None:
        return Decimal("0"), None
    if not isinstance(items, list):
        raise ValueError(f"{product_id}.{field} must be a list")
    parsed = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or "id" not in item or "apy" not in item:
            raise ValueError(f"{product_id}.{field}[{index}] needs id and apy")
        apy = decimal_value(item["apy"], f"{field}[{index}].apy", product_id)
        parsed.append((apy, str(item["id"])))
    if not parsed:
        return Decimal("0"), None
    # Deterministic label ordering makes equal-rate selection reproducible.
    maximum = max(rate for rate, _ in parsed)
    selected_id = sorted(label for rate, label in parsed if rate == maximum)[0]
    return maximum, {"id": selected_id, "apy": str(maximum)}


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be an object")
    balance = decimal_value(payload.get("balance"), "balance", "input")
    if balance <= 0:
        raise ValueError("input.balance must be greater than zero")
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("input.products must be a non-empty list")

    feasible = []
    ineligible = []
    seen_ids = set()
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("each product must be an object")
        product_id = str(product.get("id", ""))
        if not product_id:
            raise ValueError("each product needs a non-empty id")
        if product_id in seen_ids:
            raise ValueError(f"duplicate product id: {product_id}")
        seen_ids.add(product_id)

        base = decimal_value(product.get("base_apy"), "base_apy", product_id)
        opening = decimal_value(product.get("minimum_opening_deposit"), "minimum_opening_deposit", product_id, True)
        ongoing = decimal_value(product.get("minimum_ongoing_balance"), "minimum_ongoing_balance", product_id, True)
        reasons = []
        if product.get("eligible") is not True:
            reasons.append("eligibility is unverified or false")
        if opening is not None and balance < opening:
            reasons.append("balance is below minimum opening deposit")
        if ongoing is not None and balance < ongoing:
            reasons.append("balance is below minimum ongoing balance")
        if reasons:
            ineligible.append({"id": product_id, "reasons": reasons})
            continue

        checking, selected_checking = bonus_choice(product.get("checking_bonuses"), "checking_bonuses", product_id)
        card, selected_card = bonus_choice(product.get("credit_card_bonuses"), "credit_card_bonuses", product_id)
        other = Decimal("0")
        selected_other = []
        for item in product.get("other_additive_bonuses", []) or []:
            if not isinstance(item, dict) or "id" not in item or "apy" not in item:
                raise ValueError(f"{product_id}.other_additive_bonuses entries need id and apy")
            rate = decimal_value(item["apy"], "other_additive_bonuses.apy", product_id)
            other += rate
            selected_other.append({"id": str(item["id"]), "apy": str(rate)})
        effective = base + checking + card + other
        annual_estimate = (balance * effective / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        feasible.append({
            "id": product_id,
            "base_apy": str(base),
            "selected_checking_bonus": selected_checking,
            "selected_credit_card_bonus": selected_card,
            "selected_other_additive_bonuses": selected_other,
            "effective_apy": str(effective),
            "one_year_apy_based_estimate_usd": format(annual_estimate, ".2f"),
            "notes": product.get("notes", []),
        })

    feasible.sort(key=lambda item: (Decimal(item["effective_apy"]), item["id"]), reverse=True)
    best_rate = Decimal(feasible[0]["effective_apy"]) if feasible else None
    best_ids = [item["id"] for item in feasible if Decimal(item["effective_apy"]) == best_rate]
    return {
        "valid": True,
        "balance": str(balance),
        "feasible_ranked": feasible,
        "ineligible": ineligible,
        "best_effective_apy": str(best_rate) if best_rate is not None else None,
        "best_candidate_ids": sorted(best_ids),
        "disclosure": "Estimate assumes the supplied balance and qualifying conditions remain in effect for one year. It is a comparison aid, not a guarantee of credited interest.",
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        sys.exit(2)
