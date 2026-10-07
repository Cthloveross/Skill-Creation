#!/usr/bin/env python3
"""Rank feasible savings/card choices from a JSON request on stdin.

The program has no banking side effects. It does not approve a card, open an
account, link products, or transfer funds.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not number.is_finite() or number < ZERO:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return number


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def percent(value, field):
    return decimal_value(value, field)


def text_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return value


def require_object(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def highest_checking_boost(account, active_checking):
    boosts = account.get("checking_boosts_percent", {})
    require_object(boosts, "checking_boosts_percent")
    matches = []
    for checking_name in active_checking:
        if checking_name in boosts:
            matches.append((checking_name, percent(boosts[checking_name],
                                                     "checking_boosts_percent value")))
    if not matches:
        return ZERO, []
    high = max(amount for _, amount in matches)
    return high, [name for name, amount in matches if amount == high]


def main(payload):
    payload = require_object(payload, "input")
    deposit = decimal_value(payload.get("deposit"), "deposit")
    active_checking = text_list(payload.get("active_checking_accounts", []),
                                "active_checking_accounts")
    require_card = payload.get("require_card", True)
    if not isinstance(require_card, bool):
        raise ValueError("require_card must be boolean")
    accounts = payload.get("accounts")
    cards = payload.get("cards", [])
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty array")
    if not isinstance(cards, list):
        raise ValueError("cards must be an array")
    if require_card and not cards:
        raise ValueError("cards must be nonempty when require_card is true")

    normalized_cards = []
    for index, raw_card in enumerate(cards):
        card = require_object(raw_card, f"cards[{index}]")
        name = card.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"cards[{index}].name must be a nonempty string")
        status = card.get("eligibility_status", "unknown")
        if status not in {"confirmed", "unknown", "ineligible"}:
            raise ValueError("eligibility_status must be confirmed, unknown, or ineligible")
        normalized_cards.append({
            "name": name,
            "annual_fee": decimal_value(card.get("annual_fee", 0), "annual_fee"),
            "eligibility_status": status,
            "conditions": text_list(card.get("conditions", []), "conditions"),
        })
    if not require_card:
        normalized_cards.append({
            "name": None,
            "annual_fee": ZERO,
            "eligibility_status": "confirmed",
            "conditions": [],
        })

    results = []
    rejected = []
    for account_index, raw_account in enumerate(accounts):
        account = require_object(raw_account, f"accounts[{account_index}]")
        name = account.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"accounts[{account_index}].name must be a nonempty string")
        base_apy = percent(account.get("base_apy_percent"), "base_apy_percent")
        opening_minimum = decimal_value(account.get("opening_minimum", 0), "opening_minimum")
        ongoing_minimum = decimal_value(account.get("ongoing_minimum", 0), "ongoing_minimum")
        annual_account_cost = decimal_value(account.get("annual_account_cost", 0),
                                            "annual_account_cost")
        other_bonus = percent(account.get("other_additive_bonus_percent", 0),
                              "other_additive_bonus_percent")
        card_bonuses = account.get("card_bonuses_percent", {})
        require_object(card_bonuses, "card_bonuses_percent")

        reasons = []
        if deposit < opening_minimum:
            reasons.append("deposit is below opening minimum")
        if deposit < ongoing_minimum:
            reasons.append("deposit is below ongoing minimum")
        if reasons:
            rejected.append({
                "account": name,
                "feasible": False,
                "reasons": reasons,
                "deposit": float(deposit),
                "opening_minimum": float(opening_minimum),
                "ongoing_minimum": float(ongoing_minimum),
            })
            continue

        checking_bonus, selected_checking = highest_checking_boost(account, active_checking)
        for card in normalized_cards:
            if card["eligibility_status"] == "ineligible":
                continue
            card_bonus = ZERO
            if card["name"] is not None and card["name"] in card_bonuses:
                card_bonus = percent(card_bonuses[card["name"]], "card bonus")
            effective_apy = base_apy + checking_bonus + other_bonus + card_bonus
            interest = deposit * effective_apy / Decimal("100")
            costs = annual_account_cost + card["annual_fee"]
            net = interest - costs
            conditional = card["eligibility_status"] == "unknown"
            results.append({
                "account": name,
                "card": card["name"],
                "feasible": True,
                "conditional": conditional,
                "conditions": card["conditions"],
                "base_apy_percent": float(base_apy),
                "card_bonus_percent": float(card_bonus),
                "checking_bonus_percent": float(checking_bonus),
                "selected_checking_accounts": selected_checking,
                "other_additive_bonus_percent": float(other_bonus),
                "effective_apy_percent": float(effective_apy),
                "estimated_interest": float(money(interest)),
                "annual_account_cost": float(money(annual_account_cost)),
                "card_annual_fee": float(money(card["annual_fee"])),
                "annual_costs": float(money(costs)),
                "net_one_year": float(money(net)),
            })

    # Confirmed eligibility outranks otherwise identical conditional eligibility;
    # the financial result remains the primary ordering criterion.
    results.sort(key=lambda item: (
        Decimal(str(item["net_one_year"])),
        not item["conditional"],
        Decimal(str(item["effective_apy_percent"])),
    ), reverse=True)
    selected = results[0] if results else None
    return {
        "method": "constant balance × effective APY, minus disclosed annual costs",
        "deposit": float(deposit),
        "selected": selected,
        "ranked_options": results,
        "rejected_accounts": rejected,
        "notice": (
            "A conditional selection requires eligibility confirmation and is not an approval. "
            "This calculation has no banking side effects."
        ),
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
