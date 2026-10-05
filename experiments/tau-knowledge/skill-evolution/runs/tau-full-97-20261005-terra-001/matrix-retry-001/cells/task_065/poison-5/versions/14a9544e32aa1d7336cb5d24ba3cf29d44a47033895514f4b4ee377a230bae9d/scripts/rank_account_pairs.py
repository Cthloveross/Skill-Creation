#!/usr/bin/env python3
"""Rank documented, eligibility-approved checking/savings pair candidates.

Read one JSON object from stdin and write one JSON object to stdout. Rates are
percentage points. This helper has no banking, network, or filesystem side
effects beyond standard input and output.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return parsed


def required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def as_rate(value):
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered + "%"


def applicable_tier_rate(base_rate, tiers, deposit):
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    applicable = base_rate
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        threshold = number(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        rate = number(tier.get("apy"), f"tiers[{index}].apy")
        if threshold <= deposit and rate > applicable:
            applicable = rate
    return applicable


def rank(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = number(payload.get("deposit"), "deposit")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    eligible = []
    excluded = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        checking = required_text(candidate.get("checking_account_class"), "checking_account_class")
        savings = required_text(candidate.get("savings_account_class"), "savings_account_class")
        opening = number(candidate.get("opening_minimum"), "opening_minimum")
        ongoing = number(candidate.get("ongoing_minimum"), "ongoing_minimum")
        required_balance = max(opening, ongoing)
        if deposit < required_balance:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_minimum": str(required_balance),
                "reason": "deposit is below the opening or ongoing minimum",
            })
            continue

        base = applicable_tier_rate(
            number(candidate.get("base_apy"), "base_apy"),
            candidate.get("tiers", []),
            deposit,
        )
        checking_boost = number(candidate.get("checking_boost", 0), "checking_boost")
        bonuses = candidate.get("credit_card_bonuses", [])
        if not isinstance(bonuses, list):
            raise ValueError("credit_card_bonuses must be a list")
        card_bonus = max(
            (number(bonus, "credit_card_bonus") for bonus in bonuses),
            default=Decimal("0"),
        )
        direct_deposit_confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(direct_deposit_confirmed, bool):
            raise ValueError("direct_deposit_confirmed must be boolean")
        offered_direct_bonus = number(
            candidate.get("direct_deposit_bonus", 0), "direct_deposit_bonus"
        )
        direct_bonus = offered_direct_bonus if direct_deposit_confirmed else Decimal("0")
        total = base + checking_boost + card_bonus + direct_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": as_rate(total),
            "components": {
                "base_apy": as_rate(base),
                "checking_boost": as_rate(checking_boost),
                "highest_credit_card_bonus": as_rate(card_bonus),
                "direct_deposit_bonus": as_rate(direct_bonus),
            },
            "opening_minimum": str(opening),
            "ongoing_minimum": str(ongoing),
        })

    eligible.sort(
        key=lambda item: (
            -Decimal(item["total_apy"][:-1]),
            item["savings_account_class"],
            item["checking_account_class"],
        )
    )
    return {
        "deposit": str(deposit),
        "selected_plan": eligible[0] if eligible else None,
        "eligible_plans": eligible,
        "excluded_plans": excluded,
        "selection_rule": (
            "Totals include one checking boost, only the highest supplied credit-card "
            "bonus, and a direct-deposit bonus only when confirmed."
        ),
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
