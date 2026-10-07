#!/usr/bin/env python3
"""Compare normalized personal-card product facts for broad everyday spending.

Reads one JSON object from stdin and emits one JSON object on stdout. See SKILL.md
for the public input schema. This program makes no network calls and has no side
effects beyond stdout.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


VALID_AVAILABILITY = {"open", "invitation_only", "unknown"}


def decimal_value(value, field, errors, product_name, allow_null=False):
    if value is None and allow_null:
        return None
    if isinstance(value, bool):
        errors.append(f"{product_name}: {field} must be a nonnegative number.")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{product_name}: {field} must be a nonnegative number.")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(f"{product_name}: {field} must be a nonnegative number.")
        return None
    return parsed


def display_number(value, places=2):
    if value is None:
        return None
    quantum = Decimal("1").scaleb(-places)
    return float(value.quantize(quantum, rounding=ROUND_HALF_UP))


def yearly_cost(product):
    return product["annual_fee"] + (product["required_monthly_fee"] * Decimal("12"))


def product_view(product, baseline=None):
    result = {
        "name": product["name"],
        "availability": product["availability"],
        "flat_cashback_rate_pct": display_number(product["flat_cashback_rate_pct"]),
        "annual_fee": display_number(product["annual_fee"]),
        "required_monthly_fee": display_number(product["required_monthly_fee"]),
        "yearly_ongoing_cost": display_number(yearly_cost(product)),
        "required_subscription": product["required_subscription"],
        "source_ids": product["source_ids"],
    }
    if baseline is not None:
        rate_difference = product["flat_cashback_rate_pct"] - baseline["flat_cashback_rate_pct"]
        result["rate_difference_vs_no_cost_baseline_pct"] = display_number(rate_difference)
        if rate_difference > 0:
            monthly_cost = yearly_cost(product) / Decimal("12")
            break_even = monthly_cost / (rate_difference / Decimal("100"))
            result["break_even_monthly_spend_vs_no_cost_baseline"] = display_number(break_even)
        else:
            result["break_even_monthly_spend_vs_no_cost_baseline"] = None
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"Input is not valid JSON: {exc.msg}"], "warnings": []}))
        return

    errors = []
    warnings = []
    if not isinstance(payload, dict):
        print(json.dumps({"errors": ["Input must be a JSON object."], "warnings": []}))
        return

    profile = payload.get("profile")
    raw_products = payload.get("products")
    if not isinstance(profile, dict):
        errors.append("profile must be an object.")
        profile = {}
    if not isinstance(raw_products, list) or not raw_products:
        errors.append("products must be a nonempty array.")
        raw_products = []

    monthly_spend = decimal_value(profile.get("monthly_spend"), "monthly_spend", errors, "profile", allow_null=True)
    pattern = profile.get("spending_pattern")
    if pattern not in {"general", "category_specific", "unknown"}:
        errors.append("profile.spending_pattern must be general, category_specific, or unknown.")
    subscription_choice = profile.get("allow_recurring_subscription")
    if subscription_choice not in {True, False, None}:
        errors.append("profile.allow_recurring_subscription must be true, false, or null.")

    products = []
    names = set()
    for index, raw in enumerate(raw_products):
        label = f"products[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{label} must be an object.")
            continue
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}.name must be a nonempty string.")
            continue
        name = name.strip()
        if name in names:
            errors.append(f"Duplicate product name: {name}.")
            continue
        names.add(name)
        availability = raw.get("availability", "unknown")
        if availability not in VALID_AVAILABILITY:
            errors.append(f"{name}: availability must be open, invitation_only, or unknown.")
            continue
        rate = decimal_value(raw.get("flat_cashback_rate_pct"), "flat_cashback_rate_pct", errors, name, allow_null=True)
        annual_fee = decimal_value(raw.get("annual_fee"), "annual_fee", errors, name)
        monthly_fee = decimal_value(raw.get("required_monthly_fee"), "required_monthly_fee", errors, name)
        subscription = raw.get("required_subscription", False)
        if not isinstance(subscription, bool):
            errors.append(f"{name}: required_subscription must be boolean.")
            continue
        source_ids = raw.get("source_ids", [])
        if not isinstance(source_ids, list) or not all(isinstance(x, str) and x for x in source_ids):
            errors.append(f"{name}: source_ids must be an array of nonempty strings.")
            continue
        if not source_ids:
            warnings.append(f"{name}: no source IDs were supplied; cite current evidence before responding.")
        if annual_fee is None or monthly_fee is None:
            continue
        if subscription and monthly_fee == 0:
            warnings.append(f"{name}: subscription is required but its monthly cost is recorded as zero; verify current evidence.")
        if rate is None:
            warnings.append(f"{name}: no flat general-spend rate is documented; excluded from general-spend ranking.")
        products.append({
            "name": name,
            "availability": availability,
            "flat_cashback_rate_pct": rate,
            "annual_fee": annual_fee,
            "required_monthly_fee": monthly_fee,
            "required_subscription": subscription,
            "source_ids": source_ids,
        })

    eligible = [p for p in products if p["availability"] != "invitation_only" and p["flat_cashback_rate_pct"] is not None]
    unknown_availability = [p["name"] for p in eligible if p["availability"] == "unknown"]
    if unknown_availability:
        warnings.append("Availability is unconfirmed for: " + ", ".join(unknown_availability) + ".")
    if pattern in {"category_specific", "unknown"}:
        warnings.append("The ranking uses flat rates only; category-specific preferences require additional category-rate analysis.")

    no_cost = [p for p in eligible if yearly_cost(p) == 0]
    annual_fee_free = [p for p in eligible if p["annual_fee"] == 0]
    no_cost.sort(key=lambda p: (p["flat_cashback_rate_pct"], p["availability"] == "open"), reverse=True)
    annual_fee_free.sort(key=lambda p: (p["flat_cashback_rate_pct"], p["availability"] == "open"), reverse=True)

    baseline = no_cost[0] if no_cost else None
    paid = [p for p in eligible if yearly_cost(p) > 0]
    paid.sort(key=lambda p: (p["flat_cashback_rate_pct"], -yearly_cost(p)), reverse=True)

    basis = {
        "spending_pattern": pattern,
        "monthly_spend_provided": monthly_spend is not None,
        "baseline_selection_rule": "highest documented flat rate among non-invitation-only products with zero annual and required monthly cost",
        "recommendation": None,
    }
    if baseline is not None:
        basis["recommendation"] = {
            "candidate": baseline["name"],
            "reason": "best documented flat-rate candidate with no ongoing cost",
            "availability_caveat": "availability must be confirmed" if baseline["availability"] == "unknown" else None,
        }
    else:
        basis["recommendation"] = {
            "candidate": None,
            "reason": "no broadly usable zero-ongoing-cost product with a documented flat rate was supplied",
            "availability_caveat": None,
        }
        warnings.append("No zero-ongoing-cost flat-rate baseline is available; do not claim a fee-averse recommendation without explaining the tradeoff.")

    if monthly_spend is not None and baseline is not None:
        for candidate in paid:
            incremental = monthly_spend * ((candidate["flat_cashback_rate_pct"] - baseline["flat_cashback_rate_pct"]) / Decimal("100"))
            net_incremental = incremental - (yearly_cost(candidate) / Decimal("12"))
            if net_incremental > 0:
                warnings.append(f"At the supplied monthly spend, {candidate['name']} has a positive calculated incremental return versus the zero-cost baseline before taxes and exclusions.")

    output = {
        "errors": errors,
        "warnings": warnings,
        "no_ongoing_cost_ranked": [product_view(p) for p in no_cost],
        "annual_fee_free_ranked": [product_view(p) for p in annual_fee_free],
        "paid_or_subscription_alternatives": [product_view(p, baseline) for p in paid],
        "recommendation_basis": basis,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
