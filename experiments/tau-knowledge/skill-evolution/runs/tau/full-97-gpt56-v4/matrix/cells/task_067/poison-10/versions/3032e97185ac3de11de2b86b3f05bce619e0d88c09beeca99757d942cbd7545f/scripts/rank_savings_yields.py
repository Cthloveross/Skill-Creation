#!/usr/bin/env python3
"""Rank documented savings candidates without executing any banking action.

Read one JSON object from stdin and emit one JSON object to stdout. APY values are
percentage points (for example, "7.0" means 7.0%). Invalid input emits a JSON
error and exits with status 2. This helper is a comparison aid only; it does not
validate banking eligibility, documentation, or customer authorization.
"""

import json
import sys
from decimal import Decimal, DecimalException, InvalidOperation, ROUND_HALF_UP, localcontext

CENT = Decimal("0.01")
MAX_PRODUCTS = 100
MAX_BONUSES_PER_CATEGORY = 100
MAX_DECIMAL_ADJUSTED_EXPONENT = 18


def decimal_value(value, field, product_id, allow_missing=False):
    """Parse a bounded, non-negative finite decimal without accepting booleans."""
    if value is None and allow_missing:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{product_id}.{field} must be a decimal, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{product_id}.{field} is not a valid decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{product_id}.{field} must be a finite non-negative decimal")
    if result != 0 and result.adjusted() > MAX_DECIMAL_ADJUSTED_EXPONENT:
        raise ValueError(f"{product_id}.{field} is outside the supported numeric range")
    return result


def parse_bonus_list(items, field, product_id):
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError(f"{product_id}.{field} must be a list")
    if len(items) > MAX_BONUSES_PER_CATEGORY:
        raise ValueError(f"{product_id}.{field} has too many entries")
    parsed = []
    ids = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or "id" not in item or "apy" not in item:
            raise ValueError(f"{product_id}.{field}[{index}] needs id and apy")
        label = str(item["id"])
        if not label:
            raise ValueError(f"{product_id}.{field}[{index}].id must be non-empty")
        if label in ids:
            raise ValueError(f"{product_id}.{field} contains duplicate id: {label}")
        ids.add(label)
        parsed.append((decimal_value(item["apy"], f"{field}[{index}].apy", product_id), label))
    return parsed


def bonus_choice(items, field, product_id):
    parsed = parse_bonus_list(items, field, product_id)
    if not parsed:
        return Decimal("0"), None
    maximum = max(rate for rate, _ in parsed)
    # Deterministic label ordering makes an equal-rate selection reproducible.
    selected_id = sorted(label for rate, label in parsed if rate == maximum)[0]
    return maximum, {"id": selected_id, "apy": str(maximum)}


def parse_notes(value, product_id):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(note, str) for note in value):
        raise ValueError(f"{product_id}.notes must be a list of strings")
    return value


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be an object")
    balance = decimal_value(payload.get("balance"), "balance", "input")
    if balance <= 0:
        raise ValueError("input.balance must be greater than zero")
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("input.products must be a non-empty list")
    if len(products) > MAX_PRODUCTS:
        raise ValueError("input.products has too many entries")

    feasible, ineligible, seen_ids = [], [], set()
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
        other_entries = parse_bonus_list(product.get("other_additive_bonuses"), "other_additive_bonuses", product_id)
        other = sum((rate for rate, _ in other_entries), Decimal("0"))
        selected_other = [{"id": label, "apy": str(rate)} for rate, label in other_entries]
        effective = base + checking + card + other
        with localcontext() as context:
            context.prec = 60
            annual_estimate = (balance * effective / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
        feasible.append({
            "id": product_id,
            "base_apy": str(base),
            "selected_checking_bonus": selected_checking,
            "selected_credit_card_bonus": selected_card,
            "selected_other_additive_bonuses": selected_other,
            "effective_apy": str(effective),
            "one_year_apy_based_estimate_usd": format(annual_estimate, ".2f"),
            "notes": parse_notes(product.get("notes"), product_id),
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
        print(json.dumps(main(data), sort_keys=True, allow_nan=False))
    except (ValueError, TypeError, OverflowError, DecimalException, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)
