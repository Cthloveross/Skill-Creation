#!/usr/bin/env python3
"""Rank documented, eligibility-approved account pairs from JSON stdin.

All rates are percentage points. This program has no bank, network, or file
side effects other than reading stdin and writing stdout.
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


def render(value):
    value = value.normalize()
    output = format(value, "f")
    if "." in output:
        output = output.rstrip("0").rstrip(".")
    return output + "%"


def tier_rate(base, tiers, deposit):
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    applicable = base
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        minimum = number(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        rate = number(tier.get("apy"), f"tiers[{index}].apy")
        if minimum <= deposit and rate > applicable:
            applicable = rate
    return applicable


def rank(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = number(payload.get("deposit"), "deposit")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    eligible, excluded = [], []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        checking = text(candidate.get("checking_account_class"), "checking_account_class")
        savings = text(candidate.get("savings_account_class"), "savings_account_class")
        opening = number(candidate.get("opening_minimum"), "opening_minimum")
        ongoing = number(candidate.get("ongoing_minimum"), "ongoing_minimum")
        required = max(opening, ongoing)
        if deposit < required:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_minimum": str(required),
                "reason": "deposit is below sustainable minimum",
            })
            continue

        base = number(candidate.get("base_apy"), "base_apy")
        base = tier_rate(base, candidate.get("tiers", []), deposit)
        checking_boost = number(candidate.get("checking_boost", 0), "checking_boost")
        bonuses = candidate.get("credit_card_bonuses", [])
        if not isinstance(bonuses, list):
            raise ValueError("credit_card_bonuses must be a list")
        card_bonus = max((number(item, "credit_card_bonus") for item in bonuses), default=Decimal("0"))
        direct_confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(direct_confirmed, bool):
            raise ValueError("direct_deposit_confirmed must be boolean")
        direct_offered = number(candidate.get("direct_deposit_bonus", 0), "direct_deposit_bonus")
        direct_bonus = direct_offered if direct_confirmed else Decimal("0")
        total = base + checking_boost + card_bonus + direct_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": render(total),
            "components": {
                "base_apy": render(base),
                "checking_boost": render(checking_boost),
                "highest_credit_card_bonus": render(card_bonus),
                "direct_deposit_bonus": render(direct_bonus),
            },
            "opening_minimum": str(opening),
            "ongoing_minimum": str(ongoing),
        })

    eligible.sort(key=lambda item: (
        -Decimal(item["total_apy"][:-1]),
        item["savings_account_class"],
        item["checking_account_class"],
    ))
    return {
        "deposit": str(deposit),
        "selected_plan": eligible[0] if eligible else None,
        "eligible_plans": eligible,
        "excluded_plans": excluded,
        "selection_rule": "One checking boost and only the highest supplied card bonus are included.",
    }


def main():
    try:
        output = rank(json.load(sys.stdin))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
