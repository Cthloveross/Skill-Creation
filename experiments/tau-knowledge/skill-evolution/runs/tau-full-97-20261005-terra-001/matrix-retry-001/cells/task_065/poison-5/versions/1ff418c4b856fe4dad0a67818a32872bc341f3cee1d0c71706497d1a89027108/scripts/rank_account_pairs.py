#!/usr/bin/env python3
"""Rank documented checking/savings pairs using supplied runtime facts.

Reads exactly one JSON object from stdin and writes exactly one JSON object to
stdout. APY values are percentage points, not decimal rates. No banking action
is performed by this script.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, field):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return parsed


def string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def apy_text(value):
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered + "%"


def rate_for_balance(product, deposit):
    rate = decimal(product.get("base_apy", 0), "base_apy")
    tiers = product.get("tiers", [])
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        minimum = decimal(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        tier_rate = decimal(tier.get("apy"), f"tiers[{index}].apy")
        if minimum <= deposit and tier_rate > rate:
            rate = tier_rate
    return rate


def highest_card_bonus(raw, savings_class):
    if raw is None:
        return Decimal("0"), []
    if not isinstance(raw, dict):
        raise ValueError(f"credit_card_bonuses[{savings_class}] must be an object")
    highest = Decimal("0")
    labels = []
    for label, value in raw.items():
        label = string(label, "credit-card bonus label")
        bonus = decimal(value, "credit-card bonus")
        if bonus > highest:
            highest, labels = bonus, [label]
        elif bonus == highest and bonus > 0:
            labels.append(label)
    return highest, sorted(labels)


def rank(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = decimal(payload.get("deposit"), "deposit")
    direct_deposit = payload.get("direct_deposit_confirmed", False)
    if not isinstance(direct_deposit, bool):
        raise ValueError("direct_deposit_confirmed must be boolean")

    savings_products = payload.get("savings_products", [])
    checking_products = payload.get("checking_products", [])
    card_bonuses = payload.get("credit_card_bonuses", {})
    if not isinstance(savings_products, list):
        raise ValueError("savings_products must be a list")
    if not isinstance(checking_products, list):
        raise ValueError("checking_products must be a list")
    if not isinstance(card_bonuses, dict):
        raise ValueError("credit_card_bonuses must be an object")

    checking = []
    for index, item in enumerate(checking_products):
        if not isinstance(item, dict):
            raise ValueError(f"checking_products[{index}] must be an object")
        account_class = string(item.get("account_class"), "checking account_class")
        available = item.get("available", True)
        boosts = item.get("boosts", {})
        if not isinstance(available, bool):
            raise ValueError("checking availability must be boolean")
        if not isinstance(boosts, dict):
            raise ValueError("checking boosts must be an object")
        if available:
            checking.append((account_class, boosts))

    plans = []
    excluded = []
    for index, product in enumerate(savings_products):
        if not isinstance(product, dict):
            raise ValueError(f"savings_products[{index}] must be an object")
        savings_class = string(product.get("account_class"), "savings account_class")
        opening_minimum = decimal(product.get("opening_minimum", 0), "opening_minimum")
        ongoing_minimum = decimal(product.get("ongoing_minimum", 0), "ongoing_minimum")
        sustainable_minimum = max(opening_minimum, ongoing_minimum)
        if deposit < sustainable_minimum:
            excluded.append({
                "savings_account_class": savings_class,
                "reason": "deposit is below the required sustainable minimum",
                "required_minimum": str(sustainable_minimum),
            })
            continue

        requirements = product.get("requirements", [])
        if not isinstance(requirements, list) or not all(isinstance(x, str) for x in requirements):
            raise ValueError("requirements must be a list of strings")
        base = rate_for_balance(product, deposit)
        card_bonus, card_sources = highest_card_bonus(card_bonuses.get(savings_class), savings_class)
        direct_bonus = decimal(product.get("direct_deposit_bonus", 0), "direct_deposit_bonus")
        direct_required = product.get("direct_deposit_required_for_bonus", direct_bonus > 0)
        if not isinstance(direct_required, bool):
            raise ValueError("direct_deposit_required_for_bonus must be boolean")
        earned_direct_bonus = direct_bonus if (direct_deposit or not direct_required) else Decimal("0")

        for checking_class, boosts in checking:
            checking_bonus = decimal(
                boosts.get(savings_class, 0), "checking boost"
            )
            total = base + checking_bonus + card_bonus + earned_direct_bonus
            plan_requirements = list(requirements)
            if direct_bonus > 0 and direct_required and not direct_deposit:
                plan_requirements.append("direct deposit is required before its APY bonus applies")
            plans.append({
                "checking_account_class": checking_class,
                "savings_account_class": savings_class,
                "total_apy": apy_text(total),
                "components": {
                    "base_apy": apy_text(base),
                    "checking_boost": apy_text(checking_bonus),
                    "highest_credit_card_bonus": apy_text(card_bonus),
                    "direct_deposit_bonus": apy_text(earned_direct_bonus),
                },
                "credit_card_bonus_sources": card_sources,
                "opening_minimum": str(opening_minimum),
                "ongoing_minimum": str(ongoing_minimum),
                "requirements": plan_requirements,
            })

    plans.sort(key=lambda plan: (
        -Decimal(plan["total_apy"][:-1]),
        plan["savings_account_class"],
        plan["checking_account_class"],
    ))
    return {
        "deposit": str(deposit),
        "selected_plan": plans[0] if plans else None,
        "eligible_plans": plans,
        "excluded_savings_products": excluded,
        "selection_rule": (
            "Each pair uses one checking boost and the single highest supplied "
            "eligible credit-card bonus; bonuses within either category do not stack."
        ),
    }


def main():
    try:
        result = rank(json.load(sys.stdin))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
