#!/usr/bin/env python3
"""Rank disclosed cash-back offers subject to explicit customer constraints.

Reads a JSON object from stdin and writes JSON to stdout. See SKILL.md for schema.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_value(value: Any, field: str, product_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{product_name}: {field} must be numeric") from exc
    if not result.is_finite():
        raise ValueError(f"{product_name}: {field} must be finite")
    return result


def public_product(product: dict[str, Any], fee: Decimal, rate: Decimal) -> dict[str, Any]:
    return {
        "name": product["name"],
        "category": product.get("category"),
        "annual_fee": format(fee, "f"),
        "cash_back_rate_percent": format(rate, "f"),
        "rate_scope": product.get("rate_scope", "not specified"),
    }


def main(payload: dict[str, Any]) -> dict[str, Any]:
    products = payload.get("products")
    preferences = payload.get("preferences", {})
    if not isinstance(products, list):
        raise ValueError("products must be a list")
    if not isinstance(preferences, dict):
        raise ValueError("preferences must be an object")

    category = preferences.get("category", "personal")
    if not isinstance(category, str) or not category:
        raise ValueError("preferences.category must be a nonempty string")
    max_fee = decimal_value(preferences.get("max_annual_fee", 0), "max_annual_fee", "preferences")
    require_general = bool(preferences.get("requires_general_availability", True))

    qualifying: list[tuple[Decimal, dict[str, Any]]] = []
    excluded: list[dict[str, str]] = []
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(f"products[{index}] must be an object")
        name = product.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"products[{index}].name must be a nonempty string")
        fee = decimal_value(product.get("annual_fee"), "annual_fee", name)
        rate = decimal_value(product.get("cash_back_rate_percent"), "cash_back_rate_percent", name)
        if fee < 0 or rate < 0:
            raise ValueError(f"{name}: annual_fee and cash_back_rate_percent cannot be negative")

        reasons: list[str] = []
        if product.get("category") != category:
            reasons.append(f"not a {category} product")
        if fee > max_fee:
            reasons.append("standard annual fee exceeds preference")
        if product.get("available", True) is False:
            reasons.append("not available")
        if require_general and product.get("invitation_only", False):
            reasons.append("invitation-only")
        if reasons:
            excluded.append({"name": name, "reason": "; ".join(reasons)})
        else:
            qualifying.append((rate, public_product(product, fee, rate)))

    qualifying.sort(key=lambda item: (-item[0], item[1]["name"].casefold()))
    ranked = [item[1] for item in qualifying]
    best_rate = qualifying[0][0] if qualifying else None
    ties = [item for rate, item in qualifying if rate == best_rate] if best_rate is not None else []
    return {
        "recommended": ranked[0] if ranked else None,
        "tied_best_products": ties,
        "qualifying_products": ranked,
        "excluded_products": excluded,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
