#!/usr/bin/env python3
"""Rank documented checking/savings candidates without performing banking actions.

Input: one JSON object on stdin. Output: one JSON object on stdout. Numeric APY
values are percentage points rather than decimal fractions.
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


def required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")
    return value.strip()


def display(value):
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def pct(value):
    return display(value) + "%"


def tier_apy(default_apy, tiers, deposit, field):
    if not isinstance(tiers, list):
        raise ValueError(f"{field}.tiers must be a list")
    applicable = [(Decimal("0"), default_apy)]
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"{field}.tiers[{index}] must be an object")
        threshold = number(
            tier.get("minimum_balance"),
            f"{field}.tiers[{index}].minimum_balance",
        )
        apy = number(tier.get("apy"), f"{field}.tiers[{index}].apy")
        if threshold <= deposit:
            applicable.append((threshold, apy))
    return max(applicable, key=lambda item: item[0])[1]


def evaluate(payload):
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
        field = f"candidates[{index}]"
        checking = required_text(
            candidate.get("checking_account_class"),
            field + ".checking_account_class",
        )
        savings = required_text(
            candidate.get("savings_account_class"),
            field + ".savings_account_class",
        )
        opening = number(candidate.get("opening_minimum"), field + ".opening_minimum")
        ongoing = number(candidate.get("ongoing_minimum"), field + ".ongoing_minimum")
        requires_ongoing = candidate.get("apy_requires_ongoing_minimum", False)
        if not isinstance(requires_ongoing, bool):
            raise ValueError(field + ".apy_requires_ongoing_minimum must be boolean")

        if deposit < opening:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "reason": "deposit is below the opening minimum",
                "required_opening_minimum": display(opening),
            })
            continue
        if requires_ongoing and deposit < ongoing:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "reason": "documented APY requires the ongoing minimum",
                "required_ongoing_minimum": display(ongoing),
            })
            continue

        base = tier_apy(
            number(candidate.get("base_apy"), field + ".base_apy"),
            candidate.get("tiers", []),
            deposit,
            field,
        )
        checking_boost = number(
            candidate.get("checking_boost"), field + ".checking_boost"
        )
        card_bonuses = candidate.get("credit_card_bonuses", [])
        if not isinstance(card_bonuses, list):
            raise ValueError(field + ".credit_card_bonuses must be a list")
        card_bonus = max(
            (number(value, field + ".credit_card_bonuses") for value in card_bonuses),
            default=Decimal("0"),
        )
        direct_deposit_confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(direct_deposit_confirmed, bool):
            raise ValueError(field + ".direct_deposit_confirmed must be boolean")
        offered_dd_bonus = number(
            candidate.get("direct_deposit_bonus", 0),
            field + ".direct_deposit_bonus",
        )
        dd_bonus = offered_dd_bonus if direct_deposit_confirmed else Decimal("0")
        total = base + checking_boost + card_bonus + dd_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": pct(total),
            "ongoing_minimum": display(ongoing),
            "ongoing_minimum_met": deposit >= ongoing,
            "components": {
                "base_apy": pct(base),
                "checking_boost": pct(checking_boost),
                "highest_credit_card_bonus": pct(card_bonus),
                "direct_deposit_bonus": pct(dd_bonus),
            },
            "_sort_total": total,
        })

    eligible.sort(
        key=lambda plan: (
            -plan["_sort_total"],
            plan["savings_account_class"],
            plan["checking_account_class"],
        )
    )
    for plan in eligible:
        del plan["_sort_total"]

    return {
        "deposit": display(deposit),
        "selected_plan": eligible[0] if eligible else None,
        "eligible_plans": eligible,
        "excluded_plans": excluded,
        "selection_rule": (
            "One checking boost, the highest supplied credit-card bonus, and a "
            "direct-deposit bonus only when confirmed are included. Opening minimums "
            "always apply; ongoing-minimum APY exclusion applies only when explicitly declared."
        ),
    }


def main():
    try:
        print(json.dumps(evaluate(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
