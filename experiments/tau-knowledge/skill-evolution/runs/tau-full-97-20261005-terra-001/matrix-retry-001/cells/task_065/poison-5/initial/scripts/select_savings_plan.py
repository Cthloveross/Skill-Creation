#!/usr/bin/env python3
"""Rank disclosed savings/checking plans from JSON supplied on stdin.

All APY inputs use percentage points. This helper is deterministic and performs
no network, file, banking, or tool operations.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def nonnegative(value, field):
    result = number(value, field)
    if result < 0:
        raise ValueError(f"{field} must be nonnegative")
    return result


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def display(value):
    normalized = value.quantize(Decimal("0.0001")).normalize()
    return f"{normalized}%"


def applicable_apy(product, deposit):
    base = nonnegative(product.get("base_apy", 0), "base_apy")
    tiers = product.get("tiers", [])
    if tiers is None:
        tiers = []
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    best = base
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        threshold = nonnegative(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        apy = nonnegative(tier.get("apy"), f"tiers[{index}].apy")
        if threshold <= deposit and apy > best:
            best = apy
    return best


def option_eligibility(option, checking_funds):
    minimum = option.get("opening_minimum")
    if minimum is None:
        return None
    required = nonnegative(minimum, "checking opening_minimum")
    if checking_funds is None:
        return "checking opening funds were not supplied"
    if checking_funds < required:
        return f"requires {required} in checking opening funds"
    return None


def boost_for(option, savings_class):
    boosts = option.get("boosts", {})
    if not isinstance(boosts, dict):
        raise ValueError("checking boosts must be an object")
    if savings_class not in boosts:
        return Decimal("0")
    return nonnegative(boosts[savings_class], "checking boost")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = nonnegative(payload.get("deposit"), "deposit")
    checking_funds_raw = payload.get("checking_opening_funds")
    checking_funds = None if checking_funds_raw is None else nonnegative(checking_funds_raw, "checking_opening_funds")
    direct_deposit_confirmed = payload.get("direct_deposit_confirmed", False)
    if not isinstance(direct_deposit_confirmed, bool):
        raise ValueError("direct_deposit_confirmed must be boolean")

    savings = payload.get("savings_products", [])
    new_checks = payload.get("new_checking_options", [])
    existing_checks = payload.get("existing_checking_options", [])
    cards = payload.get("credit_card_bonuses", {})
    if not isinstance(savings, list) or not isinstance(new_checks, list) or not isinstance(existing_checks, list):
        raise ValueError("product and checking option fields must be lists")
    if not isinstance(cards, dict):
        raise ValueError("credit_card_bonuses must be an object")

    valid_checks = []
    excluded = []
    for source, options in (("new", new_checks), ("existing", existing_checks)):
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                raise ValueError(f"{source}_checking_options[{index}] must be an object")
            account_class = text(option.get("account_class"), "checking account_class")
            issue = option_eligibility(option, checking_funds) if source == "new" else None
            if issue:
                excluded.append({"checking_account_class": account_class, "reason": issue})
            else:
                valid_checks.append((source, account_class, option))

    max_card_bonus = Decimal("0")
    card_sources = []
    for card_name, raw_bonus in cards.items():
        label = text(card_name, "credit card name")
        bonus = nonnegative(raw_bonus, "credit card bonus")
        if bonus > max_card_bonus:
            max_card_bonus, card_sources = bonus, [label]
        elif bonus == max_card_bonus and bonus > 0:
            card_sources.append(label)

    plans = []
    for index, product in enumerate(savings):
        if not isinstance(product, dict):
            raise ValueError(f"savings_products[{index}] must be an object")
        savings_class = text(product.get("account_class"), "savings account_class")
        opening_minimum = nonnegative(product.get("opening_minimum", 0), "opening_minimum")
        ongoing_minimum = nonnegative(product.get("ongoing_minimum", 0), "ongoing_minimum")
        if deposit < opening_minimum:
            excluded.append({"savings_account_class": savings_class, "reason": f"deposit is below opening minimum of {opening_minimum}"})
            continue
        if deposit < ongoing_minimum:
            excluded.append({"savings_account_class": savings_class, "reason": f"deposit is below ongoing minimum of {ongoing_minimum}"})
            continue
        if not valid_checks:
            excluded.append({"savings_account_class": savings_class, "reason": "no eligible checking option was supplied"})
            continue

        base = applicable_apy(product, deposit)
        best_boost = Decimal("0")
        boost_sources = []
        for source, checking_class, option in valid_checks:
            boost = boost_for(option, savings_class)
            if boost > best_boost:
                best_boost, boost_sources = boost, [{"source": source, "account_class": checking_class}]
            elif boost == best_boost and boost > 0:
                boost_sources.append({"source": source, "account_class": checking_class})

        requires_dd = product.get("requires_direct_deposit", False)
        if not isinstance(requires_dd, bool):
            raise ValueError("requires_direct_deposit must be boolean")
        dd_bonus = nonnegative(product.get("direct_deposit_bonus", 0), "direct_deposit_bonus")
        applied_dd = dd_bonus if (not requires_dd or direct_deposit_confirmed) else Decimal("0")
        requirements = product.get("requirements", [])
        if not isinstance(requirements, list) or not all(isinstance(item, str) for item in requirements):
            raise ValueError("requirements must be a list of strings")
        unmet = list(requirements)
        if requires_dd and not direct_deposit_confirmed:
            unmet.append("direct deposit must be established before its bonus applies")

        total = base + best_boost + max_card_bonus + applied_dd
        plans.append({
            "savings_account_class": savings_class,
            "total_apy": display(total),
            "components": {
                "base_apy": display(base),
                "highest_checking_boost": display(best_boost),
                "highest_credit_card_bonus": display(max_card_bonus),
                "direct_deposit_bonus": display(applied_dd),
            },
            "checking_boost_sources": boost_sources,
            "credit_card_bonus_sources": card_sources,
            "conditions": unmet,
        })

    plans.sort(key=lambda item: Decimal(item["total_apy"][:-1]), reverse=True)
    return {
        "deposit": str(deposit),
        "eligible_plans": plans,
        "excluded": excluded,
        "selection_rule": "Each total uses one highest applicable checking boost and one highest applicable credit-card bonus; those components are not stacked within their category.",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
