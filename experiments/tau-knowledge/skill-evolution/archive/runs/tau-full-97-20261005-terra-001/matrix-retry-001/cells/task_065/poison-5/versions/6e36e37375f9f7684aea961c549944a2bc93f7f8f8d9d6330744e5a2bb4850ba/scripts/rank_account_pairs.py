#!/usr/bin/env python3
"""Rank documented, eligibility-approved checking/savings account candidates.

Reads one JSON object from stdin and writes one JSON object to stdout. Rates are
percentage points. This helper has no banking, network, or filesystem side
effects beyond standard input and output.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    """Return a finite, nonnegative Decimal or raise ValueError."""
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return parsed


def text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def rendered(value):
    result = format(value.normalize(), "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result or "0"


def rate(value):
    return rendered(value) + "%"


def tier_rate(base_rate, tiers, deposit):
    """Return the APY from the highest threshold the deposit qualifies for."""
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    qualified = [(Decimal("0"), base_rate)]
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        threshold = number(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        tier_apy = number(tier.get("apy"), f"tiers[{index}].apy")
        if threshold <= deposit:
            qualified.append((threshold, tier_apy))
    return max(qualified, key=lambda item: item[0])[1]


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
        checking = text(candidate.get("checking_account_class"), f"candidates[{index}].checking_account_class")
        savings = text(candidate.get("savings_account_class"), f"candidates[{index}].savings_account_class")
        opening_minimum = number(candidate.get("opening_minimum"), f"candidates[{index}].opening_minimum")
        ongoing_minimum = number(candidate.get("ongoing_minimum"), f"candidates[{index}].ongoing_minimum")
        required_minimum = max(opening_minimum, ongoing_minimum)
        if deposit < required_minimum:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_minimum": rendered(required_minimum),
                "reason": "deposit is below the opening or ongoing minimum",
            })
            continue

        base = number(candidate.get("base_apy"), f"candidates[{index}].base_apy")
        applicable_base = tier_rate(base, candidate.get("tiers", []), deposit)
        checking_boost = number(candidate.get("checking_boost", 0), f"candidates[{index}].checking_boost")

        card_bonuses = candidate.get("credit_card_bonuses", [])
        if not isinstance(card_bonuses, list):
            raise ValueError(f"candidates[{index}].credit_card_bonuses must be a list")
        card_bonus = max(
            (number(value, f"candidates[{index}].credit_card_bonuses") for value in card_bonuses),
            default=Decimal("0"),
        )

        direct_deposit_confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(direct_deposit_confirmed, bool):
            raise ValueError(f"candidates[{index}].direct_deposit_confirmed must be boolean")
        offered_direct_bonus = number(
            candidate.get("direct_deposit_bonus", 0),
            f"candidates[{index}].direct_deposit_bonus",
        )
        direct_bonus = offered_direct_bonus if direct_deposit_confirmed else Decimal("0")
        total = applicable_base + checking_boost + card_bonus + direct_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": rate(total),
            "_total": total,
            "components": {
                "base_apy": rate(applicable_base),
                "checking_boost": rate(checking_boost),
                "highest_credit_card_bonus": rate(card_bonus),
                "direct_deposit_bonus": rate(direct_bonus),
            },
            "opening_minimum": rendered(opening_minimum),
            "ongoing_minimum": rendered(ongoing_minimum),
        })

    eligible.sort(
        key=lambda item: (
            -item["_total"],
            item["savings_account_class"],
            item["checking_account_class"],
        )
    )
    for item in eligible:
        del item["_total"]
    return {
        "deposit": rendered(deposit),
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
        result = rank(json.load(sys.stdin))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
