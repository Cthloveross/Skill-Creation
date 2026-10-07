#!/usr/bin/env python3
"""Rank savings/card combinations from runtime-supplied product facts.

Input and output are JSON objects on standard input/output. See SKILL.md for schema.
"""
import json
import sys
from typing import Any, Dict, List, Tuple


def number(value: Any, field: str, errors: List[str]) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return 0.0
    if value < 0:
        errors.append(f"{field} must not be negative")
        return 0.0
    return float(value)


def bonus_for(card: Dict[str, Any], savings_name: str, label: str, errors: List[str]) -> float:
    bonuses = card.get("bonuses", {})
    if not isinstance(bonuses, dict):
        errors.append(f"{label}.bonuses must be an object")
        return 0.0
    if savings_name not in bonuses:
        return 0.0
    return number(bonuses[savings_name], f"{label}.bonuses[{savings_name!r}]", errors)


def resolve_base_apy(savings: Dict[str, Any], balance: float, errors: List[str]) -> Tuple[float, Dict[str, Any]]:
    tiers = savings.get("tiers")
    if tiers is not None:
        if not isinstance(tiers, list) or not tiers:
            errors.append(f"savings {savings.get('name', '<unnamed>')}: tiers must be a nonempty list")
            return 0.0, {}
        qualified = []
        for idx, tier in enumerate(tiers):
            if not isinstance(tier, dict):
                errors.append(f"tier {idx} must be an object")
                continue
            minimum = number(tier.get("minimum_balance"), f"tier {idx}.minimum_balance", errors)
            apy = number(tier.get("apy_pct"), f"tier {idx}.apy_pct", errors)
            if balance >= minimum:
                qualified.append((minimum, apy))
        if not qualified:
            errors.append(f"savings {savings.get('name', '<unnamed>')}: no APY tier applies at the supplied balance")
            return 0.0, {}
        minimum, apy = max(qualified, key=lambda pair: pair[0])
        return apy, {"tier_minimum_balance": minimum}
    if "base_apy_pct" not in savings:
        errors.append(f"savings {savings.get('name', '<unnamed>')} needs base_apy_pct or tiers")
        return 0.0, {}
    return number(savings["base_apy_pct"], "base_apy_pct", errors), {}


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    balance = number(payload.get("balance"), "balance", errors)
    savings_list = payload.get("savings")
    cards = payload.get("cards")
    existing_cards = payload.get("existing_cards", [])
    if not isinstance(savings_list, list) or not savings_list:
        errors.append("savings must be a nonempty list")
        savings_list = []
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty list")
        cards = []
    if not isinstance(existing_cards, list):
        errors.append("existing_cards must be a list")
        existing_cards = []

    ranked: List[Dict[str, Any]] = []
    conditional: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for savings_index, savings in enumerate(savings_list):
        if not isinstance(savings, dict):
            errors.append(f"savings[{savings_index}] must be an object")
            continue
        name = savings.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"savings[{savings_index}].name must be a nonempty string")
            continue
        opening = number(savings.get("minimum_opening_deposit", 0), f"{name}.minimum_opening_deposit", errors)
        ongoing = number(savings.get("minimum_ongoing_balance", 0), f"{name}.minimum_ongoing_balance", errors)
        unmet = []
        if balance < opening:
            unmet.append("minimum_opening_deposit")
        if balance < ongoing:
            unmet.append("minimum_ongoing_balance")
        if unmet:
            excluded.append({"savings": name, "reason": "balance below requirement", "unmet_requirements": unmet,
                             "balance": round(balance, 2), "minimum_opening_deposit": round(opening, 2),
                             "minimum_ongoing_balance": round(ongoing, 2)})
            continue

        base_apy, tier_detail = resolve_base_apy(savings, balance, errors)
        relationship = number(savings.get("relationship_bonus_pct", 0), f"{name}.relationship_bonus_pct", errors)
        checking_boosts = savings.get("checking_boosts", [])
        if not isinstance(checking_boosts, list):
            errors.append(f"{name}.checking_boosts must be a list")
            checking_boosts = []
        eligible_checking = []
        for boost_index, boost in enumerate(checking_boosts):
            if not isinstance(boost, dict):
                errors.append(f"{name}.checking_boosts[{boost_index}] must be an object")
                continue
            if boost.get("eligible") is True:
                eligible_checking.append(number(boost.get("boost_pct", 0), f"{name}.checking_boosts[{boost_index}].boost_pct", errors))
        selected_checking = max(eligible_checking, default=0.0)

        existing_bonus_values = [bonus_for(card, name, f"existing_cards[{i}]", errors)
                                 for i, card in enumerate(existing_cards) if isinstance(card, dict)]
        if len([c for c in existing_cards if not isinstance(c, dict)]):
            errors.append("every existing_cards entry must be an object")
        existing_best = max(existing_bonus_values, default=0.0)

        for card_index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"cards[{card_index}] must be an object")
                continue
            card_name = card.get("name")
            if not isinstance(card_name, str) or not card_name.strip():
                errors.append(f"cards[{card_index}].name must be a nonempty string")
                continue
            fee = number(card.get("annual_fee", 0), f"{card_name}.annual_fee", errors)
            proposed_bonus = bonus_for(card, name, f"cards[{card_index}]", errors)
            selected_card_bonus = max(existing_best, proposed_bonus)
            effective_apy = base_apy + relationship + selected_checking + selected_card_bonus
            annual_interest = balance * effective_apy / 100.0
            result = {
                "savings": name,
                "proposed_card": card_name,
                "base_apy_pct": round(base_apy, 6),
                "relationship_bonus_pct": round(relationship, 6),
                "selected_checking_boost_pct": round(selected_checking, 6),
                "proposed_card_bonus_pct": round(proposed_bonus, 6),
                "existing_best_card_bonus_pct": round(existing_best, 6),
                "selected_card_bonus_pct": round(selected_card_bonus, 6),
                "effective_apy_pct": round(effective_apy, 6),
                "annual_interest_estimate": round(annual_interest, 2),
                "new_card_annual_fee": round(fee, 2),
                "net_annual_estimate": round(annual_interest - fee, 2),
                "formula": "balance * effective_apy_pct / 100 - new_card_annual_fee",
            }
            result.update(tier_detail)
            if card.get("eligible") is True:
                ranked.append(result)
            else:
                result["eligibility_status"] = "unconfirmed_or_ineligible"
                conditional.append(result)

    ranked.sort(key=lambda item: (-item["net_annual_estimate"], -item["effective_apy_pct"], item["savings"], item["proposed_card"]))
    conditional.sort(key=lambda item: (-item["net_annual_estimate"], item["savings"], item["proposed_card"]))
    return {
        "balance": round(balance, 2),
        "ranked_eligible_combinations": ranked,
        "conditional_combinations": conditional,
        "excluded_savings": excluded,
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"balance": None, "ranked_eligible_combinations": [], "conditional_combinations": [], "excluded_savings": [], "errors": [str(exc)]}, sort_keys=True))
