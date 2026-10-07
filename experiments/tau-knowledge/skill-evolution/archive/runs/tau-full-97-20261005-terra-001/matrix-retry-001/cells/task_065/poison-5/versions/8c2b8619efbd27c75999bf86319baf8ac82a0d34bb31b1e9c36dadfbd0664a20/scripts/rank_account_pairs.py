#!/usr/bin/env python3
"""Rank already documented and eligibility-approved account-pair candidates.

Input and output are JSON on standard input/output. Rates are percentage points.
The helper has no banking, network, or filesystem side effects.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, label):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not value.is_finite() or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return value


def string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value.strip()


def display(value):
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def rate(value):
    return display(value) + "%"


def tier_rate(base, tiers, deposit, label):
    if not isinstance(tiers, list):
        raise ValueError(f"{label}.tiers must be a list")
    applicable = [(Decimal("0"), base)]
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            raise ValueError(f"{label}.tiers[{index}] must be an object")
        threshold = decimal(tier.get("minimum_balance"), f"{label}.tiers[{index}].minimum_balance")
        apy = decimal(tier.get("apy"), f"{label}.tiers[{index}].apy")
        if threshold <= deposit:
            applicable.append((threshold, apy))
    return max(applicable, key=lambda item: item[0])[1]


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
        checking = string(candidate.get("checking_account_class"), label + ".checking_account_class")
        savings = string(candidate.get("savings_account_class"), label + ".savings_account_class")
        opening = decimal(candidate.get("opening_minimum"), label + ".opening_minimum")
        ongoing = decimal(candidate.get("ongoing_minimum"), label + ".ongoing_minimum")
        needed = max(opening, ongoing)
        if deposit < needed:
            excluded.append({
                "checking_account_class": checking,
                "savings_account_class": savings,
                "required_minimum": display(needed),
                "reason": "deposit is below the opening or ongoing minimum",
            })
            continue

        base = tier_rate(decimal(candidate.get("base_apy"), label + ".base_apy"), candidate.get("tiers", []), deposit, label)
        checking_bonus = decimal(candidate.get("checking_boost"), label + ".checking_boost")
        card_values = candidate.get("credit_card_bonuses", [])
        if not isinstance(card_values, list):
            raise ValueError(label + ".credit_card_bonuses must be a list")
        card_bonus = max((decimal(v, label + ".credit_card_bonuses") for v in card_values), default=Decimal("0"))
        confirmed = candidate.get("direct_deposit_confirmed", False)
        if not isinstance(confirmed, bool):
            raise ValueError(label + ".direct_deposit_confirmed must be boolean")
        offered_direct = decimal(candidate.get("direct_deposit_bonus", 0), label + ".direct_deposit_bonus")
        direct_bonus = offered_direct if confirmed else Decimal("0")
        total = base + checking_bonus + card_bonus + direct_bonus
        eligible.append({
            "checking_account_class": checking,
            "savings_account_class": savings,
            "total_apy": rate(total),
            "components": {
                "base_apy": rate(base),
                "checking_boost": rate(checking_bonus),
                "highest_credit_card_bonus": rate(card_bonus),
                "direct_deposit_bonus": rate(direct_bonus),
            },
            "_total": total,
        })

    eligible.sort(key=lambda item: (-item["_total"], item["savings_account_class"], item["checking_account_class"]))
    for item in eligible:
        del item["_total"]
    return {
        "deposit": display(deposit),
        "selected_plan": eligible[0] if eligible else None,
        "eligible_plans": eligible,
        "excluded_plans": excluded,
        "selection_rule": "Uses one supplied checking boost, the highest supplied card bonus, and direct-deposit bonus only when confirmed.",
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
