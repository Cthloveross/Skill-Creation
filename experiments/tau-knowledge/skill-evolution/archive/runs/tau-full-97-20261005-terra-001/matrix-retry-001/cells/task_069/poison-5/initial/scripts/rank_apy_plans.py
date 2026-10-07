#!/usr/bin/env python3
"""Rank documented savings/checking/card plans from JSON stdin.

All APY values are percentage points (for example, 5.5 means 5.5%). The
caller supplies product facts from current authoritative documentation. This
script only applies explicit constraints and non-stacking card-bonus math.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def best_card(cards: List[Dict[str, Any]], predicate) -> Optional[Dict[str, Any]]:
    qualifying = []
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("each credit_card_options item must be an object")
        if predicate(card):
            qualifying.append(card)
    if not qualifying:
        return None
    return max(qualifying, key=lambda c: number(c.get("bonus_apy"), "credit card bonus_apy"))


def card_summary(card: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if card is None:
        return {"account_class": None, "bonus_apy": 0.0}
    return {
        "account_class": card.get("account_class"),
        "bonus_apy": number(card.get("bonus_apy"), "credit card bonus_apy"),
    }


def evaluate(candidate: Dict[str, Any], deposit: float, requirements: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("each candidate must be an object")
    savings = candidate.get("savings")
    checking = candidate.get("checking")
    if not isinstance(savings, dict) or not isinstance(checking, dict):
        raise ValueError("candidate must contain savings and checking objects")

    base = number(savings.get("base_apy"), "savings base_apy")
    opening_minimum = number(savings.get("opening_minimum"), "savings opening_minimum")
    ongoing_minimum = number(savings.get("ongoing_minimum"), "savings ongoing_minimum")
    atm_rebate = number(savings.get("monthly_atm_rebate"), "savings monthly_atm_rebate")
    checking_boost = number(checking.get("apy_boost", 0), "checking apy_boost")
    cards = candidate.get("credit_card_options", [])
    if not isinstance(cards, list):
        raise ValueError("credit_card_options must be a list")

    failures: List[str] = []
    if candidate.get("supported", True) is not True:
        failures.append("candidate is not supported by the supplied evidence")
    if requirements.get("automatic_overdraft_protection", False) and not checking.get("automatic_overdraft_protection", False):
        failures.append("checking account lacks required automatic overdraft protection")
    min_rebate = number(requirements.get("minimum_savings_atm_rebate", 0), "minimum_savings_atm_rebate")
    if atm_rebate < min_rebate:
        failures.append("savings ATM rebate cap is below the requested minimum")
    if deposit < opening_minimum:
        failures.append("deposit is below the savings opening minimum")
    if deposit < ongoing_minimum:
        failures.append("deposit is below the supplied ongoing minimum")

    active = best_card(cards, lambda card: card.get("active_same_profile", False) is True)
    possible = best_card(
        cards,
        lambda card: card.get("active_same_profile", False) is True
        or card.get("eligible_if_obtained", False) is True,
    )
    active_info = card_summary(active)
    possible_info = card_summary(possible)
    current_apy = round(base + checking_boost + active_info["bonus_apy"], 6)
    projected_apy = round(base + checking_boost + possible_info["bonus_apy"], 6)

    return {
        "name": candidate.get("name"),
        "eligible": not failures,
        "failures": failures,
        "savings_account_class": savings.get("account_class"),
        "checking_account_class": checking.get("account_class"),
        "base_apy": base,
        "checking_apy_boost": checking_boost,
        "selected_active_card": active_info,
        "selected_projected_card": possible_info,
        "current_effective_apy": current_apy,
        "projected_effective_apy": projected_apy,
        "projection_requires_card_action": possible is not None and possible is not active,
        "deposit_amount": deposit,
        "opening_minimum": opening_minimum,
        "ongoing_minimum": ongoing_minimum,
        "monthly_atm_rebate": atm_rebate,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    deposit = number(payload.get("deposit_amount"), "deposit_amount")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates")
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    evaluated = [evaluate(candidate, deposit, requirements) for candidate in candidates]
    eligible = [plan for plan in evaluated if plan["eligible"]]
    eligible.sort(
        key=lambda plan: (plan["projected_effective_apy"], plan["current_effective_apy"]),
        reverse=True,
    )
    ineligible = [plan for plan in evaluated if not plan["eligible"]]
    return {
        "ok": True,
        "eligible_plans": eligible,
        "ineligible_plans": ineligible,
        "recommended_plan": eligible[0] if eligible else None,
        "calculation_policy": {
            "credit_card_bonuses_stack": False,
            "highest_single_credit_card_bonus_used": True,
            "checking_boost_additive_when_supplied": True,
        },
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = main(json.loads(raw))
    except Exception as exc:  # Produce machine-readable validation failure.
        result = {"ok": False, "error": str(exc)}
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
