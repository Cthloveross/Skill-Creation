#!/usr/bin/env python3
"""Rank sustainable documented savings APY plans.

Reads one JSON object from stdin and writes one JSON object to stdout. Values are
APY percentage points. This script has no banking, network, or filesystem side effects.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return result


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def percent(value):
    return f"{value.quantize(Decimal('0.0001')).normalize()}%"


def rate_at_balance(product, deposit):
    rate = number(product.get("base_apy", 0), "base_apy")
    tiers = product.get("tiers", [])
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        threshold = number(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        tier_rate = number(tier.get("apy"), f"tiers[{index}].apy")
        if threshold <= deposit and tier_rate > rate:
            rate = tier_rate
    return rate


def highest_bonus(entries, field):
    if not isinstance(entries, dict):
        raise ValueError(f"{field} must be an object")
    highest = Decimal("0")
    labels = []
    for entry_label, raw_bonus in entries.items():
        entry_label = text(entry_label, f"{field} label")
        bonus = number(raw_bonus, field)
        if bonus > highest:
            highest, labels = bonus, [entry_label]
        elif bonus == highest and bonus > 0:
            labels.append(entry_label)
    return highest, sorted(labels)


def rank(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = number(payload.get("deposit"), "deposit")
    direct_deposit = payload.get("direct_deposit_confirmed", False)
    if not isinstance(direct_deposit, bool):
        raise ValueError("direct_deposit_confirmed must be boolean")
    products = payload.get("savings_products", [])
    checks = payload.get("checking_options", [])
    card_bonuses = payload.get("credit_card_bonuses", {})
    if not isinstance(products, list) or not isinstance(checks, list):
        raise ValueError("savings_products and checking_options must be lists")
    if not isinstance(card_bonuses, dict):
        raise ValueError("credit_card_bonuses must be an object")

    available_checks = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ValueError(f"checking_options[{index}] must be an object")
        check_class = text(check.get("account_class"), "checking account_class")
        available = check.get("available", True)
        boosts = check.get("boosts", {})
        if not isinstance(available, bool):
            raise ValueError("checking availability must be boolean")
        if not isinstance(boosts, dict):
            raise ValueError("checking boosts must be an object")
        if available:
            available_checks.append((check_class, boosts))

    eligible, excluded = [], []
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(f"savings_products[{index}] must be an object")
        savings_class = text(product.get("account_class"), "savings account_class")
        opening = number(product.get("opening_minimum", 0), "opening_minimum")
        ongoing = number(product.get("ongoing_minimum", 0), "ongoing_minimum")
        if deposit < opening or deposit < ongoing:
            minimum = max(opening, ongoing)
            excluded.append({
                "savings_account_class": savings_class,
                "reason": f"deposit below required sustainable minimum of {minimum}",
            })
            continue

        base = rate_at_balance(product, deposit)
        boost_map = {check_class: number(boosts.get(savings_class, 0), "checking boost")
                     for check_class, boosts in available_checks}
        checking_boost = max(boost_map.values(), default=Decimal("0"))
        checking_sources = sorted(
            check_class for check_class, boost in boost_map.items()
            if boost == checking_boost and boost > 0
        )

        card_bonus, card_sources = highest_bonus(
            card_bonuses.get(savings_class, {}), "credit-card bonus"
        )
        dd_bonus = number(product.get("direct_deposit_bonus", 0), "direct_deposit_bonus")
        dd_required = product.get("direct_deposit_required_for_bonus", dd_bonus > 0)
        if not isinstance(dd_required, bool):
            raise ValueError("direct_deposit_required_for_bonus must be boolean")
        earned_dd = dd_bonus if (direct_deposit or not dd_required) else Decimal("0")
        requirements = product.get("requirements", [])
        if not isinstance(requirements, list) or not all(isinstance(item, str) for item in requirements):
            raise ValueError("requirements must be a list of strings")
        requirements = list(requirements)
        if dd_bonus > 0 and dd_required and not direct_deposit:
            requirements.append("direct deposit is required before its APY bonus applies")

        total = base + checking_boost + card_bonus + earned_dd
        eligible.append({
            "savings_account_class": savings_class,
            "checking_account_classes_with_highest_boost": checking_sources,
            "total_apy": percent(total),
            "components": {
                "base_apy": percent(base),
                "highest_checking_boost": percent(checking_boost),
                "highest_credit_card_bonus": percent(card_bonus),
                "direct_deposit_bonus": percent(earned_dd),
            },
            "credit_card_bonus_sources": card_sources,
            "requirements": requirements,
        })

    eligible.sort(key=lambda item: (-Decimal(item["total_apy"][:-1]), item["savings_account_class"]))
    return {
        "deposit": str(deposit),
        "eligible_plans": eligible,
        "excluded": excluded,
        "selection_rule": "Each total includes at most one highest checking boost and at most one highest credit-card bonus; bonuses within either category do not stack.",
    }


def main():
    try:
        print(json.dumps(rank(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
