#!/usr/bin/env python3
"""Rank feasible savings/card APY combinations from JSON stdin and emit JSON stdout."""

import json
import sys
from typing import Any, Dict, List, Tuple


def number(value: Any, field: str, errors: List[str], default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return default
    if value < 0:
        errors.append(f"{field} must not be negative")
        return default
    return float(value)


def selected_base_apy(account: Dict[str, Any], deposit: float, errors: List[str]) -> Tuple[float, str]:
    tiers = account.get("apy_tiers")
    if tiers is None:
        return number(account.get("base_apy"), f"account {account.get('name', '?')}.base_apy", errors), "base"
    if not isinstance(tiers, list) or not tiers:
        errors.append(f"account {account.get('name', '?')}.apy_tiers must be a nonempty list")
        return 0.0, "invalid"
    valid = []
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            errors.append(f"account {account.get('name', '?')}.apy_tiers[{index}] must be an object")
            continue
        threshold = number(tier.get("min_balance"), f"tier {index}.min_balance", errors)
        apy = number(tier.get("apy"), f"tier {index}.apy", errors)
        if threshold <= deposit:
            valid.append((threshold, apy))
    if not valid:
        return 0.0, "no qualifying tier"
    threshold, apy = max(valid, key=lambda item: item[0])
    return apy, f"tier at or above {threshold:g}"


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    deposit = number(payload.get("deposit"), "deposit", errors)
    credit_score_raw = payload.get("credit_score")
    credit_score = None
    if credit_score_raw is not None:
        credit_score = number(credit_score_raw, "credit_score", errors)
    requires_check = payload.get("requires_documented_credit_check", False)
    if not isinstance(requires_check, bool):
        errors.append("requires_documented_credit_check must be boolean")
    accounts = payload.get("accounts")
    cards = payload.get("cards")
    boosts = payload.get("checking_boosts", {})
    existing_names = payload.get("existing_card_names", [])
    if not isinstance(accounts, list):
        errors.append("accounts must be a list")
        accounts = []
    if not isinstance(cards, list):
        errors.append("cards must be a list")
        cards = []
    if not isinstance(boosts, dict):
        errors.append("checking_boosts must be an object")
        boosts = {}
    if not isinstance(existing_names, list) or not all(isinstance(x, str) for x in existing_names):
        errors.append("existing_card_names must be a list of strings")
        existing_names = []
    if errors:
        return {"ok": False, "errors": errors}

    card_by_name = {card.get("name"): card for card in cards if isinstance(card, dict) and isinstance(card.get("name"), str)}
    rejections: List[Dict[str, str]] = []
    recommendations: List[Dict[str, Any]] = []
    assumptions = [
        "The deposit is maintained at the stated amount for one year.",
        "APY is used directly for a one-year stable-balance estimate; it is not compounded again.",
        "Only verified entries supplied in checking_boosts are treated as qualifying linked-checking boosts.",
        "Only the highest applicable credit-card APY bonus is applied."
    ]

    candidates: List[Tuple[str, Dict[str, Any], bool]] = [("No new card", {}, False)]
    for name in existing_names:
        card = card_by_name.get(name)
        if card is None:
            rejections.append({"option": name, "reason": "Existing card is not present in the supplied card catalog."})
        else:
            candidates.append((name, card, True))
    for card in cards:
        if not isinstance(card, dict) or not isinstance(card.get("name"), str):
            rejections.append({"option": "unnamed card", "reason": "Card entry is invalid."})
            continue
        if card.get("name") not in existing_names:
            candidates.append((card["name"], card, False))

    for account in accounts:
        if not isinstance(account, dict) or not isinstance(account.get("name"), str):
            rejections.append({"option": "unnamed savings account", "reason": "Account entry is invalid."})
            continue
        account_name = account["name"]
        local_errors: List[str] = []
        opening = number(account.get("min_opening_deposit", 0), f"{account_name}.min_opening_deposit", local_errors)
        ongoing = number(account.get("ongoing_min_balance", 0), f"{account_name}.ongoing_min_balance", local_errors)
        annual_account_cost = number(account.get("annual_account_cost", 0), f"{account_name}.annual_account_cost", local_errors)
        base_apy, tier_label = selected_base_apy(account, deposit, local_errors)
        boost = number(boosts.get(account_name, 0), f"checking_boosts.{account_name}", local_errors)
        if local_errors:
            rejections.append({"option": account_name, "reason": "; ".join(local_errors)})
            continue
        if deposit < opening:
            rejections.append({"option": account_name, "reason": f"Deposit is below the opening requirement of {opening:.2f}."})
            continue
        if deposit < ongoing:
            rejections.append({"option": account_name, "reason": f"Deposit is below the ongoing minimum of {ongoing:.2f} for the proposed one-year strategy."})
            continue
        bonuses = account.get("card_apy_bonuses", {})
        if not isinstance(bonuses, dict):
            rejections.append({"option": account_name, "reason": "card_apy_bonuses must be an object."})
            continue

        for candidate_name, card, is_existing in candidates:
            applicable_cards: List[Tuple[str, float]] = []
            candidate_reasons: List[str] = []
            cards_to_assess: List[Tuple[str, Dict[str, Any], bool]] = []
            for existing_name in existing_names:
                if existing_name in card_by_name:
                    cards_to_assess.append((existing_name, card_by_name[existing_name], True))
            if candidate_name != "No new card" and not is_existing:
                cards_to_assess.append((candidate_name, card, False))

            for card_name, assessed_card, _ in cards_to_assess:
                if assessed_card.get("available", True) is False:
                    candidate_reasons.append(f"{card_name} is marked unavailable")
                    continue
                documented_check = assessed_card.get("credit_check_required")
                if requires_check and documented_check is not True:
                    candidate_reasons.append(f"{card_name} lacks a documented required credit check")
                    continue
                minimum = assessed_card.get("min_credit_score")
                if minimum is not None:
                    minimum_value = number(minimum, f"{card_name}.min_credit_score", candidate_reasons)
                    if credit_score is None:
                        candidate_reasons.append(f"{card_name} requires score {minimum_value:g}, but no score was supplied")
                        continue
                    if credit_score < minimum_value:
                        candidate_reasons.append(f"{card_name} requires score {minimum_value:g}")
                        continue
                bonus = bonuses.get(card_name, 0)
                try:
                    bonus_value = float(bonus)
                except (TypeError, ValueError):
                    candidate_reasons.append(f"{card_name} has a nonnumeric APY bonus")
                    continue
                if bonus_value < 0:
                    candidate_reasons.append(f"{card_name} has a negative APY bonus")
                    continue
                applicable_cards.append((card_name, bonus_value))

            if candidate_name != "No new card" and not is_existing and candidate_reasons:
                rejections.append({"option": f"{account_name} + {candidate_name}", "reason": "; ".join(candidate_reasons)})
                continue
            if candidate_name == "No new card" and candidate_reasons:
                # Existing cards that fail documented eligibility are simply not applied.
                applicable_cards = []
            winning_card, card_bonus = max(applicable_cards, key=lambda item: item[1]) if applicable_cards else (None, 0.0)
            card_fee = 0.0
            if candidate_name != "No new card" and not is_existing:
                card_fee = number(card.get("annual_fee", 0), f"{candidate_name}.annual_fee", [])
            effective_apy = base_apy + boost + card_bonus
            annual_interest = round(deposit * effective_apy / 100.0, 2)
            known_costs = round(annual_account_cost + card_fee, 2)
            recommendations.append({
                "savings_account": account_name,
                "new_card_choice": None if candidate_name == "No new card" or is_existing else candidate_name,
                "highest_bonus_card": winning_card,
                "base_apy": round(base_apy, 6),
                "apy_tier": tier_label,
                "checking_boost": round(boost, 6),
                "credit_card_bonus": round(card_bonus, 6),
                "effective_apy": round(effective_apy, 6),
                "estimated_annual_interest": annual_interest,
                "known_annual_costs": known_costs,
                "estimated_net_annual_earnings": round(annual_interest - known_costs, 2),
                "minimum_opening_deposit": opening,
                "ongoing_minimum_balance": ongoing
            })

    recommendations.sort(key=lambda item: (item["estimated_net_annual_earnings"], item["effective_apy"]), reverse=True)
    return {"ok": True, "recommendations": recommendations, "rejections": rejections, "assumptions": assumptions}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Top-level JSON value must be an object")
        output = main(raw)
    except Exception as exc:
        output = {"ok": False, "errors": [str(exc)]}
    print(json.dumps(output, sort_keys=True))
