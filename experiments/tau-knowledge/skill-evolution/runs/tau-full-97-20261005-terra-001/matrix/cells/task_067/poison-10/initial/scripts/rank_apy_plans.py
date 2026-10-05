#!/usr/bin/env python3
"""Rank documented, compatible savings APY plans without performing banking actions.

Input is a JSON object with available_funds and plans. Output is JSON. Amounts and
rates are strings or numbers accepted by Decimal. Only bonuses explicitly marked
eligible are applied; card bonuses are reduced to the highest one.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")


def dec(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(field + " is required")
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be numeric")


def money(value):
    return format(value, ".2f")


def rate(value):
    return format(value, ".4f").rstrip("0").rstrip(".")


def assess_plan(plan, available):
    if not isinstance(plan, dict):
        return {"id": None, "viable": False, "reasons": ["Plan must be an object."]}
    plan_id = plan.get("id", "unnamed-plan")
    reasons = []
    savings = plan.get("savings")
    checking = plan.get("checking", {})
    if not isinstance(savings, dict) or not isinstance(checking, dict):
        return {"id": plan_id, "viable": False, "reasons": ["Plan requires savings and checking objects."]}
    try:
        base = dec(savings.get("base_apy_pct"), "savings.base_apy_pct")
        savings_deposit = dec(savings.get("deposit"), "savings.deposit")
        savings_open = dec(savings.get("opening_min", 0), "savings.opening_min")
        savings_ongoing = dec(savings.get("ongoing_min", 0), "savings.ongoing_min")
        checking_deposit = dec(checking.get("deposit", 0), "checking.deposit")
        checking_open = dec(checking.get("opening_min", 0), "checking.opening_min")
        checking_ongoing = dec(checking.get("ongoing_min", 0), "checking.ongoing_min")
        checking_boost = dec(checking.get("boost_pct", 0), "checking.boost_pct")
    except ValueError as exc:
        return {"id": plan_id, "viable": False, "reasons": [str(exc)]}

    if savings_deposit < savings_open:
        reasons.append("Savings deposit is below its opening minimum.")
    if savings_deposit < savings_ongoing:
        reasons.append("Savings deposit is below its ongoing minimum.")
    if checking_deposit < checking_open:
        reasons.append("Checking deposit is below its opening minimum.")
    if checking_deposit < checking_ongoing:
        reasons.append("Checking deposit is below its ongoing minimum.")
    if savings_deposit + checking_deposit > available:
        reasons.append("Combined documented deposits exceed available funds.")
    if checking.get("eligible", True) is not True:
        reasons.append("Required checking product/linkage is not confirmed eligible.")

    eligible_cards = []
    conditional_cards = []
    card_bonuses = plan.get("card_bonuses", [])
    if not isinstance(card_bonuses, list):
        reasons.append("card_bonuses must be a list.")
        card_bonuses = []
    for card in card_bonuses:
        if not isinstance(card, dict):
            continue
        try:
            bonus = dec(card.get("apy_pct"), "card_bonuses.apy_pct")
        except ValueError:
            continue
        entry = {"id": card.get("id", "unnamed-card"), "apy_pct": rate(bonus)}
        if card.get("eligible") is True:
            eligible_cards.append((bonus, entry))
        elif card.get("eligible") is None or "eligible" not in card:
            conditional_cards.append(entry)

    selected_card = max(eligible_cards, key=lambda item: item[0]) if eligible_cards else None
    card_boost = selected_card[0] if selected_card else ZERO
    effective = base + checking_boost + card_boost
    return {
        "id": plan_id,
        "viable": not reasons,
        "reasons": reasons,
        "base_apy_pct": rate(base),
        "checking_boost_pct": rate(checking_boost),
        "applied_card_bonus_pct": rate(card_boost),
        "applied_card": selected_card[1] if selected_card else None,
        "effective_apy_pct": rate(effective),
        "total_required_deposit": money(savings_deposit + checking_deposit),
        "conditional_card_opportunities": conditional_cards,
    }


def main(data):
    if not isinstance(data, dict):
        return {"selected_plan": None, "error": "Input must be a JSON object."}
    try:
        available = dec(data.get("available_funds"), "available_funds")
    except ValueError as exc:
        return {"selected_plan": None, "error": str(exc)}
    plans = data.get("plans")
    if not isinstance(plans, list):
        return {"selected_plan": None, "error": "plans must be a list."}

    assessed = [assess_plan(plan, available) for plan in plans]
    viable = [item for item in assessed if item.get("viable")]
    viable.sort(key=lambda item: Decimal(item["effective_apy_pct"]), reverse=True)
    return {
        "available_funds": money(available),
        "selected_plan": viable[0] if viable else None,
        "viable_plans_ranked": viable,
        "excluded_plans": [item for item in assessed if not item.get("viable")],
        "validation_note": "Rates apply only to documented compatible products. Verify product terms, approvals, invitation status, and same-profile linkage before relying on the result.",
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError:
        print(json.dumps({"selected_plan": None, "error": "Invalid JSON input."}))
