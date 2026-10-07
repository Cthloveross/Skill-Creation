#!/usr/bin/env python3
"""Rank documented savings/card combinations supplied as JSON on stdin.

The caller supplies customer-applicable, documented terms. This utility does not
look up products, establish eligibility, or authorize any banking action.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def decimal_number(value, field, candidate_id=None):
    """Parse a finite, nonnegative decimal field."""
    location = "input" if candidate_id is None else f"candidate {candidate_id!r}"
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{location}: {field} must be a number")
    if not number.is_finite() or number < ZERO:
        raise ValueError(f"{location}: {field} must be finite and nonnegative")
    return number


def decimal_list(value, field, candidate_id):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"candidate {candidate_id!r}: {field} must be an array")
    return [decimal_number(item, field, candidate_id) for item in value]


def money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def evaluate(candidate, deposit, term_years, constraints):
    if not isinstance(candidate, dict):
        raise ValueError("each combination must be an object")
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise ValueError("each combination requires a nonempty string id")

    base = decimal_number(candidate.get("base_apy_percent"), "base_apy_percent", candidate_id)
    card_bonuses = decimal_list(candidate.get("card_apy_bonuses_percent", []), "card_apy_bonuses_percent", candidate_id)
    checking_bonuses = decimal_list(candidate.get("checking_apy_boosts_percent", []), "checking_apy_boosts_percent", candidate_id)
    other_bonuses = decimal_list(candidate.get("other_additive_apy_bonuses_percent", []), "other_additive_apy_bonuses_percent", candidate_id)
    card_fee = decimal_number(candidate.get("annual_card_fee", 0), "annual_card_fee", candidate_id)
    subscription_fee = decimal_number(candidate.get("annual_subscription_fee", 0), "annual_subscription_fee", candidate_id)
    other_costs = decimal_number(candidate.get("other_known_annual_costs", 0), "other_known_annual_costs", candidate_id)

    rejection_reasons = []
    maximum_fee = constraints.get("max_card_annual_fee")
    if maximum_fee is not None and card_fee > maximum_fee:
        rejection_reasons.append("annual_card_fee_exceeds_maximum")
    if constraints.get("allow_paid_subscription") is False and subscription_fee > ZERO:
        rejection_reasons.append("paid_subscription_not_allowed")

    # Credit-card and checking boosts do not stack within their respective
    # categories. The caller may supply an other bonus only if documentation
    # establishes it is additive and applicable.
    applied_card = max(card_bonuses, default=ZERO)
    applied_checking = max(checking_bonuses, default=ZERO)
    applied_other = sum(other_bonuses, ZERO)
    effective_apy = base + applied_card + applied_checking + applied_other
    gross_interest = deposit * effective_apy / Decimal("100") * term_years
    recurring_costs = (card_fee + subscription_fee + other_costs) * term_years
    net_return = gross_interest - recurring_costs

    return {
        "id": candidate_id,
        "savings_account": candidate.get("savings_account"),
        "card": candidate.get("card"),
        "eligible": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "base_apy_percent": float(base),
        "applied_card_apy_bonus_percent": float(applied_card),
        "applied_checking_apy_boost_percent": float(applied_checking),
        "applied_other_additive_apy_bonus_percent": float(applied_other),
        "effective_apy_percent": float(effective_apy),
        "estimated_gross_interest": money(gross_interest),
        "estimated_recurring_costs": money(recurring_costs),
        "estimated_net_return": money(net_return),
        "notes": candidate.get("notes", []),
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")

    deposit = decimal_number(payload.get("deposit"), "deposit")
    term_years = decimal_number(payload.get("term_years", 1), "term_years")
    if deposit == ZERO or term_years == ZERO:
        raise ValueError("deposit and term_years must be greater than zero")

    raw_constraints = payload.get("constraints", {})
    if not isinstance(raw_constraints, dict):
        raise ValueError("constraints must be an object")
    constraints = dict(raw_constraints)
    if constraints.get("max_card_annual_fee") is not None:
        constraints["max_card_annual_fee"] = decimal_number(constraints["max_card_annual_fee"], "constraints.max_card_annual_fee")
    if "allow_paid_subscription" in constraints and not isinstance(constraints["allow_paid_subscription"], bool):
        raise ValueError("constraints.allow_paid_subscription must be boolean")

    combinations = payload.get("combinations")
    if not isinstance(combinations, list) or not combinations:
        raise ValueError("combinations must be a nonempty array")

    evaluated = [evaluate(item, deposit, term_years, constraints) for item in combinations]
    eligible = [item for item in evaluated if item["eligible"]]
    eligible.sort(key=lambda item: item["estimated_net_return"], reverse=True)
    best_value = eligible[0]["estimated_net_return"] if eligible else None
    best = [item for item in eligible if item["estimated_net_return"] == best_value]

    return {
        "assumptions": {
            "deposit": float(deposit),
            "term_years": float(term_years),
            "interest_method": "APY-based stable-balance estimate; APY is not compounded a second time",
            "bonus_method": "highest supplied card bonus and highest supplied checking boost; other supplied bonuses additive",
            "fee_method": "known annual recurring costs multiplied by term_years",
        },
        "eligible_ranked": eligible,
        "rejected": [item for item in evaluated if not item["eligible"]],
        "highest_net_return": best,
        "has_eligible_combination": bool(eligible),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
