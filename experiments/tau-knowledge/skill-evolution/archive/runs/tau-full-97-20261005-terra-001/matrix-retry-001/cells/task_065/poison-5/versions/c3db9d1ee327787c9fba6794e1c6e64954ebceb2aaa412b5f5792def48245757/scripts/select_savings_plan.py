#!/usr/bin/env python3
"""Deterministically rank documented savings/checking APY plans.

Read one JSON object from stdin and write one JSON object to stdout. APY values are
percentage points. This helper has no network, filesystem, or banking side effects.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, field):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return value


def label(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def fmt(value):
    value = value.quantize(Decimal("0.0001")).normalize()
    return f"{value}%"


def applicable_base(product, deposit):
    best = decimal(product.get("base_apy", 0), "base_apy")
    tiers = product.get("tiers", [])
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        threshold = decimal(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        rate = decimal(tier.get("apy"), f"tiers[{index}].apy")
        if threshold <= deposit and rate > best:
            best = rate
    return best


def highest_card_bonus(card_map, savings_class):
    entries = card_map.get(savings_class, {})
    if not isinstance(entries, dict):
        raise ValueError("credit_card_bonuses entries must be objects")
    highest = Decimal("0")
    sources = []
    for card, bonus in entries.items():
        card = label(card, "credit-card label")
        bonus = decimal(bonus, "credit-card bonus")
        if bonus > highest:
            highest, sources = bonus, [card]
        elif bonus == highest and bonus > 0:
            sources.append(card)
    return highest, sources


def rank(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = decimal(payload.get("deposit"), "deposit")
    direct_deposit = payload.get("direct_deposit_confirmed", False)
    if not isinstance(direct_deposit, bool):
        raise ValueError("direct_deposit_confirmed must be boolean")
    products = payload.get("savings_products", [])
    checks = payload.get("checking_options", [])
    card_map = payload.get("credit_card_bonuses", {})
    if not isinstance(products, list) or not isinstance(checks, list):
        raise ValueError("savings_products and checking_options must be lists")
    if not isinstance(card_map, dict):
        raise ValueError("credit_card_bonuses must be an object")

    available_checks = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise ValueError(f"checking_options[{index}] must be an object")
        checking_class = label(check.get("account_class"), "checking account_class")
        available = check.get("available", True)
        if not isinstance(available, bool):
            raise ValueError("checking available must be boolean")
        boosts = check.get("boosts", {})
        if not isinstance(boosts, dict):
            raise ValueError("checking boosts must be an object")
        if available:
            available_checks.append((checking_class, boosts))

    eligible, excluded = [], []
    for index, product in enumerate(products):
        if not isinstance(product, dict):
            raise ValueError(f"savings_products[{index}] must be an object")
        savings_class = label(product.get("account_class"), "savings account_class")
        opening = decimal(product.get("opening_minimum", 0), "opening_minimum")
        ongoing = decimal(product.get("ongoing_minimum", 0), "ongoing_minimum")
        if deposit < opening:
            excluded.append({"savings_account_class": savings_class,
                             "reason": f"deposit below opening minimum of {opening}"})
            continue
        if deposit < ongoing:
            excluded.append({"savings_account_class": savings_class,
                             "reason": f"deposit below ongoing minimum of {ongoing}"})
            continue

        base = applicable_base(product, deposit)
        best_boost, boost_sources = Decimal("0"), []
        for checking_class, boosts in available_checks:
            raw = boosts.get(savings_class, 0)
            boost = decimal(raw, "checking boost")
            if boost > best_boost:
                best_boost, boost_sources = boost, [checking_class]
            elif boost == best_boost and boost > 0:
                boost_sources.append(checking_class)

        dd_bonus = decimal(product.get("direct_deposit_bonus", 0), "direct_deposit_bonus")
        dd_required = product.get("direct_deposit_required_for_bonus", dd_bonus > 0)
        if not isinstance(dd_required, bool):
            raise ValueError("direct_deposit_required_for_bonus must be boolean")
        earned_dd = dd_bonus if (direct_deposit or not dd_required) else Decimal("0")
        conditions = product.get("requirements", [])
        if not isinstance(conditions, list) or not all(isinstance(x, str) for x in conditions):
            raise ValueError("requirements must be a list of strings")
        conditions = list(conditions)
        if dd_bonus > 0 and dd_required and not direct_deposit:
            conditions.append("direct deposit is required before its APY bonus applies")

        card_bonus, card_sources = highest_card_bonus(card_map, savings_class)
        total = base + best_boost + card_bonus + earned_dd
        eligible.append({
            "savings_account_class": savings_class,
            "checking_account_classes": boost_sources,
            "total_apy": fmt(total),
            "components": {
                "base_apy": fmt(base),
                "highest_checking_boost": fmt(best_boost),
                "highest_credit_card_bonus": fmt(card_bonus),
                "direct_deposit_bonus": fmt(earned_dd),
            },
            "credit_card_bonus_sources": card_sources,
            "conditions": conditions,
        })

    eligible.sort(key=lambda item: Decimal(item["total_apy"][:-1]), reverse=True)
    return {
        "deposit": str(deposit),
        "eligible_plans": eligible,
        "excluded": excluded,
        "selection_rule": "Totals include one highest eligible checking boost and one highest eligible card bonus; boosts within either category do not stack.",
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
