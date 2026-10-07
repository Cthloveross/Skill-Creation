#!/usr/bin/env python3
"""Rank supplied business-checking product records for advisory use.

Input JSON:
{
  "profile": {
    "requires_zero_overdraft_fee": bool,
    "reliably_maintainable_balance": number|null,
    "maximum_monthly_fee": number|null,
    "monthly_transactions": integer|null,
    "business_age_years": number|null
  },
  "products": [product-record, ...],
  "as_of": "YYYY-MM-DD"|null,
  "promotion": {
    "effective_start": "YYYY-MM-DD", "effective_end": "YYYY-MM-DD",
    "priority_order": [string, ...]
  }|null
}

Product records use the descriptive fields shown in the packaged catalog. Output JSON
contains qualifying and excluded products, estimates only where the input supports them,
and caveats. The program does not make or request any banking change.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def money(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_day(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def active_promotion(promotion, as_of):
    if not isinstance(promotion, dict):
        return []
    today = parse_day(as_of)
    start = parse_day(promotion.get("effective_start"))
    end = parse_day(promotion.get("effective_end"))
    if not (today and start and end and start <= today <= end):
        return []
    order = promotion.get("priority_order", [])
    return order if isinstance(order, list) else []


def main(payload):
    profile = payload.get("profile") or {}
    products = payload.get("products") or []
    if not isinstance(products, list):
        raise ValueError("products must be a JSON array")

    balance = money(profile.get("reliably_maintainable_balance"))
    cap = money(profile.get("maximum_monthly_fee"))
    tx_count = profile.get("monthly_transactions")
    if tx_count is not None and (not isinstance(tx_count, int) or tx_count < 0):
        raise ValueError("monthly_transactions must be a non-negative integer or null")
    age = profile.get("business_age_years")
    if age is not None and not isinstance(age, (int, float)):
        raise ValueError("business_age_years must be numeric or null")

    priority = active_promotion(payload.get("promotion"), payload.get("as_of"))
    qualifying, excluded = [], []
    for product in products:
        if not isinstance(product, dict) or not product.get("name"):
            continue
        name = str(product["name"])
        reasons, caveats = [], []
        overdraft = money(product.get("overdraft_fee"))
        if profile.get("requires_zero_overdraft_fee"):
            if overdraft is None:
                reasons.append("zero overdraft-fee policy is not documented")
            elif overdraft != Decimal("0"):
                reasons.append("has a nonzero overdraft fee")

        age_limit = product.get("formation_age_max_years")
        if age_limit is not None:
            if age is None:
                caveats.append("business-age eligibility must be confirmed")
            elif age > age_limit:
                reasons.append("business exceeds the product's formation-age limit")

        required_minimum = money(product.get("minimum_balance_requirement"))
        if required_minimum is not None:
            if balance is None:
                caveats.append("minimum-balance ability must be confirmed")
            elif balance < required_minimum:
                reasons.append("reliably maintainable balance is below the required minimum")

        fee = money(product.get("monthly_maintenance_fee"))
        if fee is None:
            fee = money(product.get("monthly_maintenance_fee_after_free_period"))
        waiver = money(product.get("maintenance_fee_waiver_balance"))
        waived = waiver is not None and balance is not None and balance >= waiver
        expected = Decimal("0") if waived else fee
        if fee is not None and waiver is not None and balance is None:
            caveats.append("maintenance-fee waiver cannot be assessed without a reliable balance")
        if fee is not None and waiver is not None and balance is not None and not waived:
            caveats.append("maintenance fee is not expected to be waived at the supplied balance")

        included = product.get("included_monthly_transactions")
        excess_fee = money(product.get("excess_transaction_fee"))
        if included is not None and included != -1:
            if tx_count is None:
                caveats.append("monthly transaction count is unknown; assess the included allowance before relying on cost")
            elif isinstance(included, int) and tx_count > included and excess_fee is not None:
                expected = (expected or Decimal("0")) + (tx_count - included) * excess_fee

        if cap is not None and expected is not None and expected > cap:
            reasons.append("known estimated monthly charge exceeds the customer's stated cap")

        record = {
            "name": name,
            "expected_known_monthly_charge": None if expected is None else float(expected),
            "maintenance_fee_waived_at_supplied_balance": waived,
            "caveats": caveats,
            "product": product,
        }
        if reasons:
            record["exclusion_reasons"] = reasons
            excluded.append(record)
        else:
            qualifying.append(record)

    rank = {str(name): i for i, name in enumerate(priority)}
    qualifying.sort(key=lambda item: (
        rank.get(item["name"], len(rank)),
        item["expected_known_monthly_charge"] is None,
        item["expected_known_monthly_charge"] if item["expected_known_monthly_charge"] is not None else 0,
        item["name"],
    ))
    return {
        "promotion_active": bool(priority),
        "promotion_priority_applied_after_eligibility": priority,
        "qualifying_products": qualifying,
        "excluded_products": excluded,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
