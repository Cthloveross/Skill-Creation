#!/usr/bin/env python3
"""Rank supplied savings APY scenarios without making banking actions.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. APY values are percentage points, not fractional rates.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a numeric value")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def display(value):
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def as_list(data, field):
    value = data.get(field, [])
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def main(data):
    deposit = number(data.get("deposit_amount"), "deposit_amount")
    if deposit < 0:
        raise ValueError("deposit_amount must be nonnegative")

    options = as_list(data, "savings_options")
    checking_accounts = as_list(data, "checking_accounts")
    checking_boosts = as_list(data, "checking_boosts")
    cards = as_list(data, "credit_card_accounts")
    card_boosts = as_list(data, "card_boosts")
    cards_confirmed = data.get("cards_confirmed")
    if not isinstance(cards_confirmed, bool):
        raise ValueError("cards_confirmed must be boolean")

    active_checking = {
        entry.get("account_class")
        for entry in checking_accounts
        if isinstance(entry, dict) and entry.get("active") is True
        and isinstance(entry.get("account_class"), str)
    }
    active_cards = {
        entry.get("card_class")
        for entry in cards
        if isinstance(entry, dict) and entry.get("active") is True
        and isinstance(entry.get("card_class"), str)
    }

    ranked = []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get("account_class"), str):
            raise ValueError("each savings option needs a string account_class")
        savings_class = option["account_class"]
        base = number(option.get("base_apy"), f"base_apy for {savings_class}")
        opening_minimum = number(
            option.get("minimum_opening_deposit", 0),
            f"minimum_opening_deposit for {savings_class}",
        )
        if opening_minimum < 0:
            raise ValueError("minimum_opening_deposit must be nonnegative")

        applicable_checking = []
        for boost in checking_boosts:
            if not isinstance(boost, dict):
                continue
            if (boost.get("savings_class") == savings_class and
                    boost.get("checking_class") in active_checking):
                amount = number(boost.get("apy_boost"), "checking apy_boost")
                applicable_checking.append((amount, boost.get("checking_class")))
        checking_amount, checking_class = max(applicable_checking, default=(Decimal("0"), None))

        applicable_cards = []
        for boost in card_boosts:
            if not isinstance(boost, dict):
                continue
            if (boost.get("savings_class") == savings_class and
                    boost.get("card_class") in active_cards):
                amount = number(boost.get("apy_boost"), "card apy_boost")
                applicable_cards.append((amount, boost.get("card_class")))
        card_amount, card_class = max(applicable_cards, default=(Decimal("0"), None))

        warnings = []
        if deposit < opening_minimum:
            warnings.append("planned deposit is below the supplied minimum opening deposit")
        if not cards_confirmed:
            warnings.append("card records have not been confirmed; card bonus is incomplete")
        if not active_checking:
            warnings.append("no active or confirmed eligible checking account was supplied")

        total = base + checking_amount + card_amount
        ranked.append({
            "account_class": savings_class,
            "base_apy": display(base),
            "selected_checking_class": checking_class,
            "selected_checking_boost": display(checking_amount),
            "selected_card_class": card_class,
            "selected_card_boost": display(card_amount),
            "estimated_total_apy": display(total),
            "minimum_opening_deposit": display(opening_minimum),
            "opening_deposit_feasible": deposit >= opening_minimum,
            "warnings": warnings,
        })

    ranked.sort(
        key=lambda item: (
            Decimal(item["estimated_total_apy"]),
            item["opening_deposit_feasible"],
            item["account_class"],
        ),
        reverse=True,
    )
    return {
        "deposit_amount": display(deposit),
        "cards_confirmed": cards_confirmed,
        "ranked_options": ranked,
        "action_required": "Obtain the customer's exact account_class confirmation before opening any account.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
