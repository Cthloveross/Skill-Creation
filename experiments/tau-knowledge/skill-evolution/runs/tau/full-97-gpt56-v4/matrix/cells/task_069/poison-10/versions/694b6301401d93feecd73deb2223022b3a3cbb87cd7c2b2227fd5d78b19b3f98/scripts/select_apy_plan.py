#!/usr/bin/env python3
"""Rank documented savings/checking/card combinations from JSON stdin.

All APY inputs and outputs are percentage points, not decimal fractions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def as_flag(value, field):
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be true or false")
    return value


def emit_error(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be an object")
    balance = number(data.get("balance"), "balance")
    if balance < 0:
        raise ValueError("balance must not be negative")
    require_overdraft = as_flag(data.get("require_overdraft_transfer"), "require_overdraft_transfer")
    savings = data.get("savings")
    checking = data.get("checking")
    cards = data.get("cards", [])
    if not isinstance(savings, list) or not savings:
        raise ValueError("savings must be a nonempty list")
    if not isinstance(checking, list) or not checking:
        raise ValueError("checking must be a nonempty list")
    if not isinstance(cards, list):
        raise ValueError("cards must be a list")

    card_choices = [{"card_class": None, "eligible": True, "approval_required": False}]
    for card in cards:
        if not isinstance(card, dict) or not isinstance(card.get("card_class"), str) or not card["card_class"]:
            raise ValueError("each card needs a nonempty card_class")
        card_choices.append({
            "card_class": card["card_class"],
            "eligible": as_flag(card.get("eligible"), f"cards[{card['card_class']}].eligible"),
            "approval_required": as_flag(card.get("approval_required", False), f"cards[{card['card_class']}].approval_required"),
        })

    candidates = []
    excluded = []
    for saving in savings:
        if not isinstance(saving, dict) or not isinstance(saving.get("account_class"), str) or not saving["account_class"]:
            raise ValueError("each savings item needs a nonempty account_class")
        s_name = saving["account_class"]
        base = number(saving.get("base_apy"), f"{s_name}.base_apy")
        opening = number(saving.get("minimum_opening_deposit", 0), f"{s_name}.minimum_opening_deposit")
        ongoing = number(saving.get("minimum_ongoing_balance", 0), f"{s_name}.minimum_ongoing_balance")
        balance_eligible = as_flag(saving.get("eligible_for_balance"), f"{s_name}.eligible_for_balance")
        relationship_eligible = as_flag(saving.get("relationship_bonus_eligible", False), f"{s_name}.relationship_bonus_eligible")
        relationship = number(saving.get("relationship_bonus", 0), f"{s_name}.relationship_bonus") if relationship_eligible else Decimal("0")
        bonuses = saving.get("card_bonuses", {})
        if not isinstance(bonuses, dict):
            raise ValueError(f"{s_name}.card_bonuses must be an object")
        if not balance_eligible or balance < opening or balance < ongoing:
            excluded.append({"savings_account": s_name, "reason": "balance or tier eligibility not established"})
            continue

        for check in checking:
            if not isinstance(check, dict) or not isinstance(check.get("account_class"), str) or not check["account_class"]:
                raise ValueError("each checking item needs a nonempty account_class")
            c_name = check["account_class"]
            if not as_flag(check.get("eligible"), f"{c_name}.eligible"):
                excluded.append({"checking_account": c_name, "savings_account": s_name, "reason": "checking eligibility not established"})
                continue
            supports = as_flag(check.get("supports_overdraft_transfer"), f"{c_name}.supports_overdraft_transfer")
            linkable = check.get("overdraft_link_eligible_savings", [])
            if not isinstance(linkable, list) or not all(isinstance(x, str) for x in linkable):
                raise ValueError(f"{c_name}.overdraft_link_eligible_savings must be a list of names")
            if require_overdraft and (not supports or (s_name not in linkable and "*" not in linkable)):
                excluded.append({"checking_account": c_name, "savings_account": s_name, "reason": "does not establish required overdraft-transfer linkage"})
                continue
            check_bonus_map = check.get("savings_bonuses", {})
            if not isinstance(check_bonus_map, dict):
                raise ValueError(f"{c_name}.savings_bonuses must be an object")
            check_bonus = number(check_bonus_map.get(s_name, 0), f"{c_name}.savings_bonuses[{s_name}]")
            fee = number(check.get("overdraft_transfer_fee", 0), f"{c_name}.overdraft_transfer_fee")

            for card in card_choices:
                if not card["eligible"]:
                    continue
                card_bonus = Decimal("0") if card["card_class"] is None else number(bonuses.get(card["card_class"], 0), f"{s_name}.card bonus")
                total = base + check_bonus + relationship + card_bonus
                candidates.append({
                    "checking_account": c_name,
                    "savings_account": s_name,
                    "card": card["card_class"],
                    "apy_percentage_points": float(total),
                    "components_percentage_points": {
                        "base_apy": float(base),
                        "checking_bonus": float(check_bonus),
                        "relationship_bonus": float(relationship),
                        "card_bonus": float(card_bonus),
                    },
                    "overdraft_transfer_fee": float(fee) if supports else None,
                    "conditional_on_card_approval": bool(card["card_class"] and card["approval_required"]),
                })

    candidates.sort(key=lambda x: (-x["apy_percentage_points"], x["checking_account"], x["savings_account"], x["card"] or ""))
    return {"ok": True, "best": candidates[0] if candidates else None, "candidates": candidates, "excluded": excluded}


if __name__ == "__main__":
    try:
        main_input = json.load(sys.stdin)
        print(json.dumps(main(main_input), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        emit_error(str(exc))
