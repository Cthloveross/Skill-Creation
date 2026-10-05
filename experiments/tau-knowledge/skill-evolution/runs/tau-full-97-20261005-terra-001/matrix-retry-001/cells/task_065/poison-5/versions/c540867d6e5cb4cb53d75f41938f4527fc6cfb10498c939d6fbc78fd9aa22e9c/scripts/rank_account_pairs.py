#!/usr/bin/env python3
"""Rank documented, eligibility-approved checking/savings candidates.

Read one JSON object from stdin and write one JSON object to stdout. Rates are
percentage points. This helper performs no banking, network, or filesystem action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return number


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def shown(value):
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def percent(value):
    return shown(value) + "%"


def applicable_base(default_apy, tiers, deposit, label):
    if not isinstance(tiers, list):
        raise ValueError(f"{label}.tiers must be a list")
    choices = [(Decimal("0"), default_apy)]
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"{label}.tiers[{index}] must be an object")
        threshold = decimal(tier.get("minimum_balance"), f"{label}.tiers[{index}].minimum_balance")
        tier_apy = decimal(tier.get("apy"), f"{label}.tiers[{index}].apy")
        if threshold <= deposit:
            choices.append((threshold, tier_apy))
    return max(choices, key=lambda item: item[0])[1]


def rank(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = decimal(payload.get("deposit"), "deposit")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    eligible, excluded = [], []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        label = f"candidates[{index}]"
        checking = text(candidate.get("checking_account_class"), label + ".checking_account_class")
        savings = text(candidate.get("savings_account_class"), label + ".savings_account_class")
        opening = decimal(candidate.get("opening_minimum"), label + ".opening_minimum")
        ongoing = decimal(candidate.get("ongoing_minimum"), label + ".ongoing_minimum")
        requires_ongoing = candidate.get("apy_requires_ongoing_minimum", False)
        if not isinstance(requires_ongoing, bool):
            raise ValueError(label + ".apy_requires_ongoing_minimum must be boolean")
        if deposit < opening:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_opening_minimum": shown(opening),
                "reason": "deposit is below the opening minimum",
            })
            continue
        if requires_ongoing and deposit < ongoing:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_ongoing_minimum": shown(ongoing),
                "reason": "documented APY requires the ongoing minimum",
            })
            continue

        base = applicable_base(
            decimal(candidate.get("base_apy"), label + ".base_apy"),
            candidate.get("tiers", []), deposit, label,
        )
        checking_boost = decimal(candidate.get("checking_boost"), label + ".checking_boost")
        card_values = candidate.get("credit_card_bonuses", [])
        if not isinstance(card_values, list):
            raise ValueError(label + ".credit_card_bonuses must be a list")
        card_bonus = max(
            (decimal(item, label + ".credit_card_bonuses") for item in card_values),
            default=Decimal("0"),
        )
        confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(confirmed, bool):
            raise ValueError(label + ".direct_deposit_confirmed must be boolean")
        offered_direct = decimal(candidate.get("direct_deposit_bonus", 0), label + ".direct_deposit_bonus")
        direct_bonus = offered_direct if confirmed else Decimal("0")
        total = base + checking_boost + card_bonus + direct_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": percent(total),
            "ongoing_minimum": shown(ongoing),
            "ongoing_minimum_met": deposit >= ongoing,
            "components": {
                "base_apy": percent(base),
                "checking_boost": percent(checking_boost),
                "highest_credit_card_bonus": percent(card_bonus),
                "direct_deposit_bonus": percent(direct_bonus),
            },
            "_total": total,
        })

    eligible.sort(key=lambda item: (-item["_total"], item["savings_account_class"], item["checking_account_class"]))
    for item in eligible:
        del item["_total"]
    return {
        "deposit": shown(deposit),
        "selected_plan": eligible[0] if eligible else None,
        "eligible_plans": eligible,
        "excluded_plans": excluded,
        "selection_rule": "Uses one supplied checking boost, the highest supplied card bonus, and direct-deposit bonus only when confirmed. Opening minimum is mandatory; ongoing-minimum APY eligibility is enforced only when specified.",
    }


def main():
    try:
        print(json.dumps(rank(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
