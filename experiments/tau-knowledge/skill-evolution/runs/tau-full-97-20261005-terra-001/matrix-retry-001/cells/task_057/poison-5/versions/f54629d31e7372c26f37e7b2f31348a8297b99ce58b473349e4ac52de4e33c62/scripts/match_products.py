#!/usr/bin/env python3
"""Filter documented checking products against structured customer requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. No network or
banking actions are performed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def as_decimal(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        text = str(value).strip().replace("$", "").replace(",", "")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def main(payload):
    needs = payload.get("needs")
    products = payload.get("products")
    if not isinstance(needs, dict) or not isinstance(products, list):
        return {"error": "needs must be an object and products must be an array"}

    require_no_fee = needs.get("no_overdraft_fee") is True
    require_protection = needs.get("overdraft_protection") is True
    minimum_days = needs.get("minimum_early_direct_deposit_days")
    if minimum_days is not None and (isinstance(minimum_days, bool) or not isinstance(minimum_days, (int, float))):
        return {"error": "minimum_early_direct_deposit_days must be a number or null"}

    matching = []
    excluded = []
    for product in products:
        if not isinstance(product, dict):
            excluded.append({"account_class": None, "reasons": ["product is not an object"]})
            continue
        name = product.get("account_class")
        reasons = []
        if not isinstance(name, str) or not name.strip():
            reasons.append("missing official account_class")
        if product.get("evidence_complete") is not True:
            reasons.append("documented evidence is incomplete")
        ordinary_fee = as_decimal(product.get("ordinary_overdraft_fee"))
        if require_no_fee and ordinary_fee != Decimal("0"):
            reasons.append("does not document a $0 ordinary overdraft fee")
        if require_protection:
            if product.get("supports_overdraft_protection") is not True:
                reasons.append("does not document overdraft protection")
            elif as_decimal(product.get("overdraft_protection_transfer_fee")) is None:
                reasons.append("overdraft-protection transfer fee is unknown")
        if minimum_days is not None:
            days = product.get("early_direct_deposit_days")
            if isinstance(days, bool) or not isinstance(days, (int, float)) or days < minimum_days:
                reasons.append("does not document the requested early-direct-deposit timing")
        if reasons:
            excluded.append({"account_class": name, "reasons": reasons})
        else:
            matching.append(product)

    matching.sort(key=lambda item: (as_decimal(item.get("overdraft_protection_transfer_fee")) or Decimal("999999"), item["account_class"].casefold()))
    return {
        "matching_products": matching,
        "recommended_account_class": matching[0]["account_class"] if matching else None,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(supplied), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
