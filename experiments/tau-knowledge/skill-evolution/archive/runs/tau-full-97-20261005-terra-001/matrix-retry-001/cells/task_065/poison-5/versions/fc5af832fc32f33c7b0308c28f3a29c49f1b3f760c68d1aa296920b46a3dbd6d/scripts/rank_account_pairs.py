#!/usr/bin/env python3
"""Rank documented, eligibility-approved checking/savings candidates.

Read one JSON object from stdin and emit one JSON object to stdout. Rates are
percentage points. This helper performs no banking, network, or file actions.
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
    result = format(value.normalize(), "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result or "0"


def percent(value):
    return render(value) + "%"


def applicable_tier(base_apy, tiers, deposit):
    if not isinstance(tiers, list):
        raise ValueError("tiers must be a list")
    qualifying = [(Decimal("0"), base_apy)]
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"tiers[{index}] must be an object")
        minimum = number(tier.get("minimum_balance"), f"tiers[{index}].minimum_balance")
        apy = number(tier.get("apy"), f"tiers[{index}].apy")
        if minimum <= deposit:
            qualifying.append((minimum, apy))
    return max(qualifying, key=lambda item: item[0])[1]


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
        prefix = f"candidates[{index}]"
        checking = text(candidate.get("checking_account_class"), prefix + ".checking_account_class")
        savings = text(candidate.get("savings_account_class"), prefix + ".savings_account_class")
        opening_minimum = number(candidate.get("opening_minimum"), prefix + ".opening_minimum")
        ongoing_minimum = number(candidate.get("ongoing_minimum"), prefix + ".ongoing_minimum")
        required_minimum = max(opening_minimum, ongoing_minimum)
        if deposit < required_minimum:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_minimum": render(required_minimum),
                "reason": "deposit is below the opening or ongoing minimum",
            })
            continue

        base = number(candidate.get("base_apy"), prefix + ".base_apy")
        base = applicable_tier(base, candidate.get("tiers", []), deposit)
        checking_boost = number(candidate.get("checking_boost"), prefix + ".checking_boost")

        card_values = candidate.get("credit_card_bonuses", [])
        if not isinstance(card_values, list):
            raise ValueError(prefix + ".credit_card_bonuses must be a list")
        card_bonus = max(
            (number(value, prefix + ".credit_card_bonuses") for value in card_values),
            default=Decimal("0"),
        )

        confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(confirmed, bool):
            raise ValueError(prefix + ".direct_deposit_confirmed must be boolean")
        offered_direct_bonus = number(
            candidate.get("direct_deposit_bonus", 0),
            prefix + ".direct_deposit_bonus",
        )
        direct_bonus = offered_direct_bonus if confirmed else Decimal("0")
        total = base + checking_boost + card_bonus + direct_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": percent(total),
            "_total": total,
            "components": {
                "base_apy": percent(base),
                "checking_boost": percent(checking_boost),
                "highest_credit_card_bonus": percent(card_bonus),
                "direct_deposit_bonus": percent(direct_bonus),
            },
            "opening_minimum": render(opening_minimum),
            "ongoing_minimum": render(ongoing_minimum),
        })

    eligible.sort(key=lambda item: (
        -item["_total"], item["savings_account_class"], item["checking_account_class"]
    ))
    for item in eligible:
        del item["_total"]
    return {
        "deposit": render(deposit),
        "selected_plan": eligible[0] if eligible else None,
        "eligible_plans": eligible,
        "excluded_plans": excluded,
        "selection_rule": (
            "Totals include one supplied checking boost, the highest supplied credit-card "
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
