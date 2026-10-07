#!/usr/bin/env python3
"""Rank documented credit-card facts for broad everyday spending.

Reads one JSON object from stdin and emits one JSON object on stdout. It makes no
network calls and has no side effects. See SKILL.md for the input schema.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

AVAILABILITY = {"open", "invitation_only", "unknown"}
PATTERNS = {"general", "category_specific", "unknown"}


def number(value, label, errors, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool):
        errors.append(f"{label} must be a nonnegative number.")
        return None
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a nonnegative number.")
        return None
    if not value.is_finite() or value < 0:
        errors.append(f"{label} must be a nonnegative number.")
        return None
    return value


def shown(value, places=2):
    if value is None:
        return None
    return float(value.quantize(Decimal("1").scaleb(-places), rounding=ROUND_HALF_UP))


def yearly_cost(product):
    return product["annual_fee"] + product["required_monthly_fee"] * Decimal("12")


def sort_key(product):
    # A documented open product wins ties over an availability-unknown product.
    return (product["flat_cashback_rate_pct"], product["availability"] == "open", -yearly_cost(product))


def view(product, baseline=None):
    result = {
        "name": product["name"],
        "availability": product["availability"],
        "flat_cashback_rate_pct": shown(product["flat_cashback_rate_pct"]),
        "annual_fee": shown(product["annual_fee"]),
        "required_monthly_fee": shown(product["required_monthly_fee"]),
        "required_subscription": product["required_subscription"],
        "yearly_ongoing_cost": shown(yearly_cost(product)),
        "source_ids": product["source_ids"],
    }
    if baseline is not None:
        difference = product["flat_cashback_rate_pct"] - baseline["flat_cashback_rate_pct"]
        result["rate_difference_vs_baseline_pct"] = shown(difference)
        if difference > 0:
            monthly_cost = yearly_cost(product) / Decimal("12")
            result["break_even_monthly_spend_vs_baseline"] = shown(
                monthly_cost / (difference / Decimal("100"))
            )
        else:
            result["break_even_monthly_spend_vs_baseline"] = None
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"Input is not valid JSON: {exc.msg}"], "warnings": []}))
        return

    errors, warnings = [], []
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

    pattern = profile.get("spending_pattern")
    if pattern not in PATTERNS:
        errors.append("profile.spending_pattern must be general, category_specific, or unknown.")
    monthly_spend = number(profile.get("monthly_spend"), "profile.monthly_spend", errors, True)
    avoid_fee = profile.get("avoid_annual_fee")
    if not isinstance(avoid_fee, bool):
        errors.append("profile.avoid_annual_fee must be boolean.")
    allow_subscription = profile.get("allow_recurring_subscription")
    if allow_subscription not in (True, False, None):
        errors.append("profile.allow_recurring_subscription must be true, false, or null.")
    pays_full = profile.get("pays_statement_balance_in_full")
    if not isinstance(pays_full, bool):
        errors.append("profile.pays_statement_balance_in_full must be boolean.")

    products, unranked, names = [], [], set()
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
        if availability not in AVAILABILITY:
            errors.append(f"{name}: availability must be open, invitation_only, or unknown.")
            continue
        rate = number(raw.get("flat_cashback_rate_pct"), f"{name}.flat_cashback_rate_pct", errors, True)
        annual = number(raw.get("annual_fee"), f"{name}.annual_fee", errors)
        monthly = number(raw.get("required_monthly_fee"), f"{name}.required_monthly_fee", errors)
        subscription = raw.get("required_subscription", False)
        sources = raw.get("source_ids", [])
        if not isinstance(subscription, bool):
            errors.append(f"{name}.required_subscription must be boolean.")
            continue
        if not isinstance(sources, list) or not all(isinstance(x, str) and x for x in sources):
            errors.append(f"{name}.source_ids must be an array of nonempty strings.")
            continue
        if annual is None or monthly is None:
            continue
        product = {
            "name": name, "availability": availability, "flat_cashback_rate_pct": rate,
            "annual_fee": annual, "required_monthly_fee": monthly,
            "required_subscription": subscription, "source_ids": sources,
        }
        if not sources:
            warnings.append(f"{name}: no source IDs supplied; verify and cite current product evidence.")
        if subscription and monthly == 0:
            warnings.append(f"{name}: a required subscription has zero recorded cost; verify the evidence.")
        if availability == "invitation_only":
            unranked.append({"name": name, "reason": "invitation_only", "source_ids": sources})
        elif rate is None:
            unranked.append({"name": name, "reason": "no_documented_general_rate", "source_ids": sources})
        else:
            products.append(product)

    if pattern != "general":
        warnings.append("Ranking uses documented general rates; category-specific preferences need category-rate analysis.")
    if any(p["availability"] == "unknown" for p in products):
        warnings.append("Some ranked products have unconfirmed availability; do not present them as assuredly obtainable.")

    no_cost = [p for p in products if yearly_cost(p) == 0]
    paid = [p for p in products if yearly_cost(p) > 0]
    no_cost.sort(key=sort_key, reverse=True)
    paid.sort(key=sort_key, reverse=True)
    baseline = no_cost[0] if no_cost else None

    compatible_paid = []
    for product in paid:
        conflicts = []
        if avoid_fee is True and product["annual_fee"] > 0:
            conflicts.append("annual_fee_declined")
        if allow_subscription is False and product["required_subscription"]:
            conflicts.append("required_subscription_declined")
        if conflicts:
            unranked.append({"name": product["name"], "reason": ",".join(conflicts), "source_ids": product["source_ids"]})
        else:
            compatible_paid.append(product)

    recommendation = None
    if baseline is not None:
        recommendation = {
            "candidate": baseline["name"],
            "reason": "highest documented general rate among non-invitation-only products with zero ongoing cost",
            "availability_caveat": baseline["availability"] == "unknown",
        }
    else:
        warnings.append("No zero-ongoing-cost general-rate baseline was supplied; explain the tradeoff rather than asserting a fee-averse winner.")

    if monthly_spend is None and paid:
        warnings.append("Monthly spend is unknown; paid alternatives must not be described as net-reward winners.")
    if pays_full is True:
        warnings.append("Customer plans to pay in full; APR on carried balances is not used in this reward ranking.")

    output = {
        "errors": errors,
        "warnings": warnings,
        "no_ongoing_cost_ranked": [view(p) for p in no_cost],
        "paid_or_subscription_alternatives": [view(p, baseline) for p in paid],
        "compatible_paid_alternatives": [view(p, baseline) for p in compatible_paid],
        "unranked_products": unranked,
        "recommendation_basis": {
            "spending_pattern": pattern,
            "monthly_spend_provided": monthly_spend is not None,
            "avoid_annual_fee": avoid_fee,
            "allow_recurring_subscription": allow_subscription,
            "recommendation": recommendation,
        },
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
