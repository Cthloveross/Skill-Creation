#!/usr/bin/env python3
"""Rank evidence-grounded savings/card combinations provided as JSON on stdin.

This helper performs arithmetic only. Callers must extract product terms from the
current task, establish applicability, and obtain authorization for any banking
action separately. Output is JSON; validation failures are JSON on stdout and a
nonzero exit status.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def number(value, field, context="input", allow_zero=True):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{context}: {field} must be a number") from exc
    if not parsed.is_finite() or parsed < ZERO or (not allow_zero and parsed == ZERO):
        qualifier = "positive" if not allow_zero else "finite and nonnegative"
        raise ValueError(f"{context}: {field} must be {qualifier}")
    return parsed


def number_list(value, field, candidate_id):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"candidate {candidate_id!r}: {field} must be an array")
    return [number(item, field, f"candidate {candidate_id!r}") for item in value]


def as_money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def evaluate(candidate, deposit, years, constraints):
    if not isinstance(candidate, dict):
        raise ValueError("each combination must be an object")
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("each combination requires a nonempty string id")

    context = f"candidate {candidate_id!r}"
    base = number(candidate.get("base_apy_percent"), "base_apy_percent", context)
    card_bonuses = number_list(candidate.get("card_apy_bonuses_percent", []), "card_apy_bonuses_percent", candidate_id)
    checking_bonuses = number_list(candidate.get("checking_apy_boosts_percent", []), "checking_apy_boosts_percent", candidate_id)
    other_bonuses = number_list(candidate.get("other_additive_apy_bonuses_percent", []), "other_additive_apy_bonuses_percent", candidate_id)
    card_fee = number(candidate.get("annual_card_fee", 0), "annual_card_fee", context)
    subscription_fee = number(candidate.get("annual_subscription_fee", 0), "annual_subscription_fee", context)
    other_costs = number(candidate.get("other_known_annual_costs", 0), "other_known_annual_costs", context)

    rejected_for = []
    fee_ceiling = constraints.get("max_card_annual_fee")
    if fee_ceiling is not None and card_fee > fee_ceiling:
        rejected_for.append("annual_card_fee_exceeds_maximum")
    if constraints.get("allow_paid_subscription") is False and subscription_fee > ZERO:
        rejected_for.append("paid_subscription_not_allowed")

    # Product-category boosts do not stack. The caller supplies only bonuses that
    # are documented and applicable; this enforces highest-only selection.
    applied_card_bonus = max(card_bonuses, default=ZERO)
    applied_checking_bonus = max(checking_bonuses, default=ZERO)
    applied_other_bonus = sum(other_bonuses, ZERO)
    effective_apy = base + applied_card_bonus + applied_checking_bonus + applied_other_bonus
    gross_interest = deposit * effective_apy * years / Decimal("100")
    recurring_costs = (card_fee + subscription_fee + other_costs) * years
    net_return = gross_interest - recurring_costs

    return {
        "id": candidate_id,
        "savings_account": candidate.get("savings_account"),
        "card": candidate.get("card"),
        "eligible": not rejected_for,
        "rejection_reasons": rejected_for,
        "base_apy_percent": float(base),
        "applied_card_apy_bonus_percent": float(applied_card_bonus),
        "applied_checking_apy_boost_percent": float(applied_checking_bonus),
        "applied_other_additive_apy_bonus_percent": float(applied_other_bonus),
        "effective_apy_percent": float(effective_apy),
        "estimated_gross_interest": as_money(gross_interest),
        "estimated_recurring_costs": as_money(recurring_costs),
        "estimated_net_return": as_money(net_return),
        "notes": candidate.get("notes", []),
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")

    deposit = number(payload.get("deposit"), "deposit", allow_zero=False)
    years = number(payload.get("term_years", 1), "term_years", allow_zero=False)

    constraints = payload.get("constraints", {})
    if not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    constraints = dict(constraints)
    if constraints.get("max_card_annual_fee") is not None:
        constraints["max_card_annual_fee"] = number(
            constraints["max_card_annual_fee"], "constraints.max_card_annual_fee"
        )
    if "allow_paid_subscription" in constraints and not isinstance(
        constraints["allow_paid_subscription"], bool
    ):
        raise ValueError("constraints.allow_paid_subscription must be boolean")

    candidates = payload.get("combinations")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("combinations must be a nonempty array")

    evaluated = [evaluate(candidate, deposit, years, constraints) for candidate in candidates]
    eligible = [item for item in evaluated if item["eligible"]]
    eligible.sort(key=lambda item: item["estimated_net_return"], reverse=True)
    top_return = eligible[0]["estimated_net_return"] if eligible else None

    return {
        "assumptions": {
            "deposit": float(deposit),
            "term_years": float(years),
            "interest_method": "APY-based stable-balance estimate; APY is not compounded a second time",
            "bonus_method": "highest supplied card bonus and highest supplied checking boost; other supplied bonuses are additive",
            "fee_method": "known annual recurring costs multiplied by term_years",
        },
        "eligible_ranked": eligible,
        "rejected": [item for item in evaluated if not item["eligible"]],
        "highest_net_return": [
            item for item in eligible if item["estimated_net_return"] == top_return
        ],
        "has_eligible_combination": bool(eligible),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
