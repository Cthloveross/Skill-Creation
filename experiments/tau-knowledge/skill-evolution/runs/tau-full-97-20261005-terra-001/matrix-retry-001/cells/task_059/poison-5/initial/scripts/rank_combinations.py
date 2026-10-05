#!/usr/bin/env python3
"""Rank documented savings/card combinations from JSON stdin.

This program performs arithmetic only. Callers must supply current, documented,
customer-applicable product terms and must not interpret its output as approval
or an authorization to act.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")


def number(value, field, candidate_id=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        where = "input" if candidate_id is None else "candidate " + repr(candidate_id)
        raise ValueError(f"{where}: {field} must be a number")
    if not result.is_finite() or result < 0:
        where = "input" if candidate_id is None else "candidate " + repr(candidate_id)
        raise ValueError(f"{where}: {field} must be a finite nonnegative number")
    return result


def bonus_list(value, field, candidate_id):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"candidate {candidate_id!r}: {field} must be an array")
    return [number(item, field, candidate_id) for item in value]


def as_json_decimal(value):
    return float(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def evaluate(candidate, deposit, term_years, constraints):
    if not isinstance(candidate, dict):
        raise ValueError("each combination must be an object")
    candidate_id = candidate.get("id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("each combination requires a nonempty string id")

    base = number(candidate.get("base_apy_percent"), "base_apy_percent", candidate_id)
    card_bonuses = bonus_list(candidate.get("card_apy_bonuses_percent", []),
                              "card_apy_bonuses_percent", candidate_id)
    checking_bonuses = bonus_list(candidate.get("checking_apy_boosts_percent", []),
                                  "checking_apy_boosts_percent", candidate_id)
    other_bonuses = bonus_list(candidate.get("other_additive_apy_bonuses_percent", []),
                               "other_additive_apy_bonuses_percent", candidate_id)
    card_fee = number(candidate.get("annual_card_fee", 0), "annual_card_fee", candidate_id)
    subscription_fee = number(candidate.get("annual_subscription_fee", 0),
                              "annual_subscription_fee", candidate_id)
    other_costs = number(candidate.get("other_known_annual_costs", 0),
                         "other_known_annual_costs", candidate_id)

    reasons = []
    max_card_fee = constraints.get("max_card_annual_fee")
    if max_card_fee is not None and card_fee > max_card_fee:
        reasons.append("annual_card_fee_exceeds_maximum")
    if constraints.get("allow_paid_subscription") is False and subscription_fee > 0:
        reasons.append("paid_subscription_not_allowed")

    applied_card = max(card_bonuses, default=Decimal("0"))
    applied_checking = max(checking_bonuses, default=Decimal("0"))
    applied_other = sum(other_bonuses, Decimal("0"))
    effective_apy = base + applied_card + applied_checking + applied_other

    # APY represents annual yield. For nonannual terms this is a labeled
    # linear estimate; callers must ensure fee proration is appropriate.
    gross_interest = deposit * (effective_apy / Decimal("100")) * term_years
    recurring_costs = (card_fee + subscription_fee + other_costs) * term_years
    net_return = gross_interest - recurring_costs

    result = {
        "id": candidate_id,
        "savings_account": candidate.get("savings_account"),
        "card": candidate.get("card"),
        "eligible": not reasons,
        "rejection_reasons": reasons,
        "base_apy_percent": float(base),
        "applied_card_apy_bonus_percent": float(applied_card),
        "applied_checking_apy_boost_percent": float(applied_checking),
        "applied_other_additive_apy_bonus_percent": float(applied_other),
        "effective_apy_percent": float(effective_apy),
        "estimated_gross_interest": as_json_decimal(gross_interest),
        "estimated_recurring_costs": as_json_decimal(recurring_costs),
        "estimated_net_return": as_json_decimal(net_return),
        "notes": candidate.get("notes", []),
    }
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON must be an object")
    deposit = number(payload.get("deposit"), "deposit")
    term_years = number(payload.get("term_years", 1), "term_years")
    if deposit == 0 or term_years == 0:
        raise ValueError("deposit and term_years must be greater than zero")
    combinations = payload.get("combinations")
    if not isinstance(combinations, list) or not combinations:
        raise ValueError("combinations must be a nonempty array")
    raw_constraints = payload.get("constraints", {})
    if not isinstance(raw_constraints, dict):
        raise ValueError("constraints must be an object")
    constraints = dict(raw_constraints)
    if "max_card_annual_fee" in constraints and constraints["max_card_annual_fee"] is not None:
        constraints["max_card_annual_fee"] = number(
            constraints["max_card_annual_fee"], "constraints.max_card_annual_fee"
        )
    if "allow_paid_subscription" in constraints and not isinstance(
        constraints["allow_paid_subscription"], bool
    ):
        raise ValueError("constraints.allow_paid_subscription must be boolean")

    evaluated = [evaluate(item, deposit, term_years, constraints) for item in combinations]
    eligible = [item for item in evaluated if item["eligible"]]
    eligible.sort(key=lambda item: item["estimated_net_return"], reverse=True)
    best_value = eligible[0]["estimated_net_return"] if eligible else None
    best = [item for item in eligible if item["estimated_net_return"] == best_value]

    return {
        "assumptions": {
            "deposit": float(deposit),
            "term_years": float(term_years),
            "interest_method": "APY-based estimate for a stable balance; APY bonuses use highest card and highest checking boost",
            "fee_method": "known recurring annual costs multiplied by term_years",
        },
        "eligible_ranked": eligible,
        "rejected": [item for item in evaluated if not item["eligible"]],
        "highest_net_return": best,
        "has_eligible_combination": bool(eligible),
    }


if __name__ == "__main__":
    try:
        input_payload = json.load(sys.stdin)
        print(json.dumps(main(input_payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
