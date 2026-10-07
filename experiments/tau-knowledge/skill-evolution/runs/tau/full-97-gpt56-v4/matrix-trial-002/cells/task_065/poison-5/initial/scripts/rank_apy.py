#!/usr/bin/env python3
"""Rank eligible savings/checking APY combinations from JSON on stdin.

This tool is calculation-only: it does not query systems or perform banking actions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

VALID_STATUS = {"eligible", "ineligible", "unknown"}


def decimal(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a numeric value")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{field} must be a finite non-negative value")
        return None
    return result


def status(item, label, errors):
    value = item.get("eligibility", "eligible")
    if value not in VALID_STATUS:
        errors.append(f"{label}.eligibility must be eligible, ineligible, or unknown")
        return "unknown"
    return value


def fmt(value):
    # Fixed-point decimal representation, without scientific notation.
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def product_rate(product, balance, errors):
    if "apy_tiers" not in product:
        if "base_apy" not in product:
            errors.append(f"savings product {product.get('name', '<unnamed>')} needs base_apy or apy_tiers")
            return None
        return decimal(product["base_apy"], f"{product.get('name', '<unnamed>')}.base_apy", errors)
    tiers = product["apy_tiers"]
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"{product.get('name', '<unnamed>')}.apy_tiers must be a nonempty list")
        return None
    matches = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            errors.append(f"tier {index} for {product.get('name', '<unnamed>')} must be an object")
            continue
        minimum = decimal(tier.get("min_balance", 0), "tier.min_balance", errors)
        maximum = None if tier.get("max_balance") is None else decimal(tier["max_balance"], "tier.max_balance", errors)
        apy = decimal(tier.get("apy"), "tier.apy", errors)
        if minimum is None or apy is None or (maximum is not None and maximum < minimum):
            continue
        if balance >= minimum and (maximum is None or balance <= maximum):
            matches.append(apy)
    if len(matches) != 1:
        errors.append(f"tiers for {product.get('name', '<unnamed>')} must match the stated balance exactly once")
        return None
    return matches[0]


def main(data):
    errors = []
    if not isinstance(data, dict):
        return {"errors": ["input must be a JSON object"]}
    balance = decimal(data.get("savings_balance"), "savings_balance", errors)
    products = data.get("savings_products")
    if not isinstance(products, list) or not products:
        errors.append("savings_products must be a nonempty list")
        products = []
    checking = data.get("checking_accounts", [])
    if not isinstance(checking, list):
        errors.append("checking_accounts must be a list")
        checking = []
    boosts = data.get("linked_boosts", [])
    bonuses = data.get("other_bonuses", [])
    policies = data.get("bonus_policies", {})
    if not isinstance(boosts, list):
        errors.append("linked_boosts must be a list")
        boosts = []
    if not isinstance(bonuses, list):
        errors.append("other_bonuses must be a list")
        bonuses = []
    if not isinstance(policies, dict) or any(v not in {"add", "highest"} for v in policies.values()):
        errors.append("bonus_policies values must be add or highest")
        policies = {}

    product_names = set()
    products_by_name = {}
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"]:
            errors.append("every savings product needs a nonempty name")
            continue
        if product["name"] in product_names:
            errors.append(f"duplicate savings product name: {product['name']}")
        product_names.add(product["name"])
        products_by_name[product["name"]] = product
    checking_by_name = {}
    for account in checking:
        if not isinstance(account, dict) or not isinstance(account.get("name"), str) or not account["name"]:
            errors.append("every checking account needs a nonempty name")
            continue
        checking_by_name[account["name"]] = account

    # Validate referred product names early to prevent quietly discarding a rate.
    for boost in boosts:
        if not isinstance(boost, dict):
            errors.append("each linked_boost must be an object")
            continue
        if boost.get("savings") not in product_names:
            errors.append(f"linked boost references unknown savings product: {boost.get('savings')}")
        if boost.get("checking") not in checking_by_name:
            errors.append(f"linked boost references unknown checking account: {boost.get('checking')}")
    for bonus in bonuses:
        if not isinstance(bonus, dict):
            errors.append("each other_bonus must be an object")
        elif bonus.get("savings") not in product_names:
            errors.append(f"other bonus references unknown savings product: {bonus.get('savings')}")
    if errors or balance is None:
        return {"errors": errors}

    ranked = []
    excluded = []
    uncertainties = []
    for name, product in products_by_name.items():
        p_status = status(product, f"savings product {name}", errors)
        opening = decimal(product.get("opening_minimum", 0), f"{name}.opening_minimum", errors)
        ongoing = decimal(product.get("ongoing_minimum", 0), f"{name}.ongoing_minimum", errors)
        base = product_rate(product, balance, errors)
        if errors or opening is None or ongoing is None or base is None:
            continue
        if p_status == "ineligible":
            excluded.append({"savings": name, "reason": "savings-product eligibility is not met"})
            continue
        if p_status == "unknown":
            uncertainties.append(f"Eligibility for savings product {name} is unknown")
            continue
        if balance < opening or balance < ongoing:
            requirement = "opening minimum" if balance < opening else "ongoing minimum"
            excluded.append({"savings": name, "reason": f"balance is below the {requirement}"})
            continue

        # A base-rate candidate remains useful even if no checking option applies.
        choices = [(None, Decimal("0"), [])]
        known_linked = []
        for boost in boosts:
            if not isinstance(boost, dict) or boost.get("savings") != name:
                continue
            b_status = status(boost, "linked boost", errors)
            rate = decimal(boost.get("apy"), "linked boost apy", errors)
            account = checking_by_name.get(boost.get("checking"))
            account_status = status(account, f"checking account {boost.get('checking')}", errors) if account else "unknown"
            label = f"linked boost {boost.get('checking')} + {name}"
            if b_status == "unknown" or account_status == "unknown":
                uncertainties.append(f"{label} has unknown eligibility")
            elif b_status == "eligible" and account_status == "eligible" and rate is not None:
                known_linked.append((boost.get("checking"), rate, label))
        if known_linked:
            maximum = max(item[1] for item in known_linked)
            # Retain ties because more than one checking choice can produce the same APY.
            choices = [(check, rate, [label]) for check, rate, label in known_linked if rate == maximum]

        applicable_other = []
        for bonus in bonuses:
            if not isinstance(bonus, dict) or bonus.get("savings") != name:
                continue
            b_status = status(bonus, "other bonus", errors)
            label = bonus.get("label") or bonus.get("group", "other bonus")
            rate = decimal(bonus.get("apy"), f"other bonus {label} apy", errors)
            if b_status == "unknown":
                uncertainties.append(f"Bonus {label} for {name} has unknown eligibility")
            elif b_status == "eligible" and rate is not None:
                applicable_other.append((bonus.get("group", "other"), rate, label))
        grouped = {}
        for group, rate, label in applicable_other:
            grouped.setdefault(group, []).append((rate, label))
        other_total = Decimal("0")
        other_labels = []
        for group, values in grouped.items():
            if policies.get(group, "add") == "highest":
                high = max(rate for rate, _ in values)
                selected = [(rate, label) for rate, label in values if rate == high]
                # Tied values represent alternatives, not stacked bonuses.
                other_total += high
                other_labels.extend(label for _, label in selected)
            else:
                other_total += sum(rate for rate, _ in values)
                other_labels.extend(label for _, label in values)

        for check, linked_rate, linked_labels in choices:
            ranked.append({
                "savings": name,
                "checking": check,
                "base_apy_percent": fmt(base),
                "linked_checking_bonus_percent": fmt(linked_rate),
                "other_bonus_percent": fmt(other_total),
                "effective_apy_percent": fmt(base + linked_rate + other_total),
                "selected_bonuses": linked_labels + other_labels,
            })

    if errors:
        return {"errors": errors}
    ranked.sort(key=lambda item: Decimal(item["effective_apy_percent"]), reverse=True)
    top = []
    if ranked:
        highest = Decimal(ranked[0]["effective_apy_percent"])
        top = [item for item in ranked if Decimal(item["effective_apy_percent"]) == highest]
    return {
        "errors": [],
        "ranked_candidates": ranked,
        "top_candidates": top,
        "excluded": excluded,
        "uncertainties": sorted(set(uncertainties)),
        "absolute_highest_supported": bool(ranked) and not uncertainties,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"invalid JSON input: {exc.msg}"]}))
    except Exception as exc:  # Keep a malformed runtime input from producing non-JSON output.
        print(json.dumps({"errors": [f"calculator failure: {type(exc).__name__}: {exc}"]}))
