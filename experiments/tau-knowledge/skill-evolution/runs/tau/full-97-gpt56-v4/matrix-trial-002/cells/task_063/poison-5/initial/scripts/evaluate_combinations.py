#!/usr/bin/env python3
"""Rank documented savings/card combinations from JSON provided on stdin.

Input schema is documented in SKILL.md. Numeric APY fields are percentage points.
Output contains eligible rankings, exclusions, and calculation assumptions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc


def optional_decimal(value, field):
    return None if value is None else decimal_value(value, field)


def bool_or_none(value, field):
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{field} must be true, false, or null")
    return value


def tier_for_balance(account, balance):
    tiers = account.get("apy_tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError(f"{account.get('name', 'savings account')}.apy_tiers must be nonempty")
    eligible = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError("each APY tier must be an object")
        minimum = decimal_value(tier.get("minimum_balance"), f"apy_tiers[{index}].minimum_balance")
        apy = decimal_value(tier.get("apy_percent"), f"apy_tiers[{index}].apy_percent")
        if balance >= minimum:
            eligible.append((minimum, apy))
    if not eligible:
        return None
    return max(eligible, key=lambda item: item[0])


def card_eligibility(card, customer):
    reasons = []
    name = card.get("name", "unnamed card")
    score = optional_decimal(customer.get("credit_score"), "customer.credit_score")
    minimum_score = optional_decimal(card.get("minimum_credit_score"), f"{name}.minimum_credit_score")
    if minimum_score is not None:
        if score is None:
            reasons.append("credit score is unknown")
        elif score < minimum_score:
            reasons.append(f"credit score is below documented minimum of {minimum_score}")

    subscription = bool_or_none(customer.get("premium_subscription"), "customer.premium_subscription")
    if card.get("requires_premium_subscription", False):
        if subscription is not True:
            reasons.append("required premium subscription is not confirmed active")

    if card.get("invitation_only", False) and not card.get("invited", False):
        reasons.append("invitation-only eligibility is not confirmed")

    wants_check = customer.get("requires_credit_check", False)
    if wants_check and card.get("requires_credit_check") is not True:
        reasons.append("does not meet preference for a card that requires a credit check")
    return reasons


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    customer = payload.get("customer")
    accounts = payload.get("savings_accounts")
    cards = payload.get("credit_cards")
    if not isinstance(customer, dict) or not isinstance(accounts, list) or not isinstance(cards, list):
        raise ValueError("customer, savings_accounts, and credit_cards are required")

    balance = decimal_value(customer.get("available_balance"), "customer.available_balance")
    if balance < ZERO:
        raise ValueError("customer.available_balance cannot be negative")

    eligible = []
    excluded = []
    card_failures = {}
    for card in cards:
        if not isinstance(card, dict) or not card.get("name"):
            raise ValueError("every credit card needs a name")
        card_failures[card["name"]] = card_eligibility(card, customer)

    for account in accounts:
        if not isinstance(account, dict) or not account.get("name"):
            raise ValueError("every savings account needs a name")
        account_name = account["name"]
        opening = decimal_value(account.get("opening_minimum", 0), f"{account_name}.opening_minimum")
        ongoing = decimal_value(account.get("ongoing_minimum", 0), f"{account_name}.ongoing_minimum")
        if balance < opening or balance < ongoing:
            required = max(opening, ongoing)
            excluded.append({"savings_account": account_name, "credit_card": None,
                             "reason": f"available balance is below required amount of {required}"})
            continue
        tier = tier_for_balance(account, balance)
        if tier is None:
            excluded.append({"savings_account": account_name, "credit_card": None,
                             "reason": "available balance does not qualify for any documented APY tier"})
            continue
        tier_minimum, base_apy = tier
        fixed = decimal_value(account.get("fixed_bonus_percent", 0), f"{account_name}.fixed_bonus_percent")
        checking = decimal_value(account.get("checking_boost_percent", 0), f"{account_name}.checking_boost_percent")
        dd = ZERO
        if customer.get("direct_deposit_active", False):
            dd = decimal_value(account.get("direct_deposit_bonus_percent", 0),
                               f"{account_name}.direct_deposit_bonus_percent")

        for card in cards:
            card_name = card["name"]
            failures = card_failures[card_name]
            if failures:
                excluded.append({"savings_account": account_name, "credit_card": card_name,
                                 "reason": "; ".join(failures)})
                continue
            bonuses = card.get("apy_bonuses", {})
            if not isinstance(bonuses, dict) or account_name not in bonuses:
                excluded.append({"savings_account": account_name, "credit_card": card_name,
                                 "reason": "no documented card APY bonus for this savings account"})
                continue
            card_bonus = decimal_value(bonuses[account_name], f"{card_name}.apy_bonuses[{account_name}]")
            effective = base_apy + fixed + checking + dd + card_bonus
            annual = (balance * effective / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
            eligible.append({
                "savings_account": account_name,
                "credit_card": card_name,
                "tier_minimum_balance": float(tier_minimum),
                "base_apy_percent": float(base_apy),
                "bonus_breakdown_percent": {
                    "fixed": float(fixed), "checking": float(checking),
                    "direct_deposit": float(dd), "credit_card": float(card_bonus)
                },
                "effective_apy_percent": float(effective),
                "estimated_one_year_interest": float(annual)
            })

    eligible.sort(key=lambda row: (Decimal(str(row["estimated_one_year_interest"])),
                                   Decimal(str(row["effective_apy_percent"]))), reverse=True)
    for i, row in enumerate(eligible):
        row["rank"] = i + 1
        if i == 0:
            row["difference_from_best_interest"] = 0.0
        else:
            best = Decimal(str(eligible[0]["estimated_one_year_interest"]))
            current = Decimal(str(row["estimated_one_year_interest"]))
            row["difference_from_best_interest"] = float((best - current).quantize(CENT))

    return {
        "eligible_combinations": eligible,
        "excluded": excluded,
        "assumptions": [
            "Estimated annual interest equals constant balance multiplied by stated effective APY.",
            "APY bonus fields are additive percentage points supplied from verified product terms.",
            "The input must include only checking boosts that the exact documented checking/savings pairing qualifies for.",
            "The tool evaluates eligibility from supplied facts; it does not approve products or perform banking actions."
        ]
    }


if __name__ == "__main__":
    try:
        result = main(json.load(sys.stdin))
        print(json.dumps(result, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
