#!/usr/bin/env python3
"""Rank feasible documented savings/card combinations.

Reads one JSON object from stdin and writes one JSON object to stdout. Uses only the
packaged financial-combination catalog and Python's standard library.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def as_text(value):
    # Plain fixed-point strings keep the JSON output suitable for money displays.
    return format(value, "f")


def card_reasons(card, data):
    reasons = []
    score = data.get("credit_score")
    minimum = card.get("minimum_credit_score")
    if minimum is not None:
        if score is None:
            reasons.append("credit score is not supplied")
        elif Decimal(str(score)) < Decimal(str(minimum)):
            reasons.append(f"credit score is below the required {minimum}")
    if card.get("requires_premium_subscription") and not data.get("has_premium_subscription", False):
        reasons.append("requires an active premium subscription")
    if card.get("requires_invitation"):
        explicit = data.get("card_eligibility", {}).get(card["name"])
        if explicit is not True:
            reasons.append("requires an invitation confirmed through card_eligibility")
    if card.get("requires_explicit_eligibility_confirmation"):
        explicit = data.get("card_eligibility", {}).get(card["name"])
        if explicit is not True:
            reasons.append("requires explicit eligibility confirmation through card_eligibility")
    return reasons


def highest_checking_boost(boosts, account_name):
    matches = []
    for boost in boosts:
        if not isinstance(boost, dict):
            continue
        if boost.get("savings_account") == account_name:
            try:
                value = number(boost.get("apy_percent"), "checking_boosts[].apy_percent")
            except ValueError:
                continue
            matches.append(value)
    return max(matches) if matches else Decimal("0")


def additive_bonus(bonuses, account_name):
    total = Decimal("0")
    labels = []
    for bonus in bonuses:
        if not isinstance(bonus, dict) or bonus.get("savings_account") != account_name:
            continue
        value = number(bonus.get("apy_percent"), "other_additive_bonuses[].apy_percent")
        total += value
        labels.append(bonus.get("label", "verified additive bonus"))
    return total, labels


def main(data):
    balance = number(data.get("balance"), "balance")
    if balance == 0:
        raise ValueError("balance must be greater than zero for an earnings comparison")
    catalog_path = Path(__file__).resolve().parents[1] / "references" / "financial-combination-catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    boosts = data.get("checking_boosts", [])
    other_bonuses = data.get("other_additive_bonuses", [])
    if not isinstance(boosts, list) or not isinstance(other_bonuses, list):
        raise ValueError("checking_boosts and other_additive_bonuses must be arrays")
    if not isinstance(data.get("card_eligibility", {}), dict):
        raise ValueError("card_eligibility must be an object")

    subscription = data.get("subscription", {})
    if not isinstance(subscription, dict):
        raise ValueError("subscription must be an object")
    subscription_cost = number(
        subscription.get("monthly_cost", catalog["premium_subscription"]["monthly_cost"]),
        "subscription.monthly_cost",
    )
    charge_subscription = bool(subscription.get("incremental_for_comparison", False))

    cards = catalog["cards"]
    excluded = []
    results = []
    warnings = [
        "Results assume the supplied balance is held for the full year and all product eligibility remains active.",
        "Operational eligibility to open a personal savings account is not verified by this calculator.",
        "Cash back, account maintenance fees caused by falling below minimums, taxes, and undocumented boosts are excluded."
    ]
    if not charge_subscription:
        warnings.append("The premium subscription cost is excluded as non-incremental; set subscription.incremental_for_comparison to true to allocate it to a required card.")

    for account in catalog["savings_accounts"]:
        account_reasons = []
        opening = account.get("opening_minimum")
        ongoing = account.get("ongoing_minimum")
        listed_apy_minimum = account.get("minimum_balance_for_listed_apy")
        if opening is not None and balance < Decimal(str(opening)):
            account_reasons.append(f"balance is below the opening minimum of {opening}")
        if ongoing is not None and balance < Decimal(str(ongoing)):
            account_reasons.append(f"balance is below the ongoing minimum of {ongoing}")
        if listed_apy_minimum is not None and balance < Decimal(str(listed_apy_minimum)):
            account_reasons.append("balance does not qualify for the catalog's listed APY tier")

        for card in cards:
            reasons = list(account_reasons) + card_reasons(card, data)
            bonus_value = account["card_bonuses"].get(card["name"])
            if bonus_value is None:
                reasons.append("no account-specific card APY bonus is documented in the packaged catalog")
            if reasons:
                excluded.append({"savings_account": account["name"], "credit_card": card["name"], "reasons": reasons})
                continue

            base = Decimal(str(account["base_apy_percent"]))
            card_bonus = Decimal(str(bonus_value))
            checking_bonus = highest_checking_boost(boosts, account["name"])
            extra_bonus, extra_labels = additive_bonus(other_bonuses, account["name"])
            effective_apy = base + card_bonus + checking_bonus + extra_bonus
            interest = money(balance * effective_apy / Decimal("100"))
            annual_fee = Decimal(str(card["annual_fee"]))
            membership_cost = Decimal("0")
            if card.get("requires_premium_subscription") and charge_subscription:
                membership_cost = money(subscription_cost * Decimal("12"))
            annual_costs = money(annual_fee + membership_cost)
            net = money(interest - annual_costs)
            results.append({
                "savings_account": account["name"],
                "credit_card": card["name"],
                "effective_apy_percent": as_text(effective_apy),
                "estimated_interest": as_text(interest),
                "annual_costs": as_text(annual_costs),
                "estimated_net_one_year": as_text(net),
                "components": {
                    "base_apy_percent": as_text(base),
                    "selected_card_bonus_percent": as_text(card_bonus),
                    "selected_checking_boost_percent": as_text(checking_bonus),
                    "other_additive_bonus_percent": as_text(extra_bonus),
                    "card_annual_fee": as_text(money(annual_fee)),
                    "allocated_membership_cost": as_text(membership_cost),
                    "other_bonus_labels": extra_labels
                }
            })

    results.sort(key=lambda item: (Decimal(item["estimated_net_one_year"]), Decimal(item["effective_apy_percent"])), reverse=True)
    if not results:
        warnings.append("No fully documented feasible combination was found with the supplied facts. Review excluded options and provide missing eligibility only when verified.")
    return {
        "assumptions": {
            "balance": as_text(balance),
            "period": "one year",
            "interest_method": "balance multiplied by effective APY",
            "premium_subscription_cost_is_incremental": charge_subscription,
            "card_bonus_policy": "only the highest applicable card bonus is used; combinations contain one selected card"
        },
        "ranked_options": results,
        "excluded": excluded,
        "warnings": warnings
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
