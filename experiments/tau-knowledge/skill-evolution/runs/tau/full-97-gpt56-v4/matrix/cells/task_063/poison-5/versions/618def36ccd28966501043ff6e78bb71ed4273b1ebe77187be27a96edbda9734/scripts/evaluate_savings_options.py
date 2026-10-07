#!/usr/bin/env python3
"""Rank supplied savings/card combinations without making banking actions.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the public input schema.  Monetary output is rounded to cents and
rate output is expressed in percentage points.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def number(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def choose_rate(rates, deposit, label):
    if not isinstance(rates, list) or not rates:
        raise ValueError(f"{label}.rates must contain at least one tier")
    eligible = []
    for index, tier in enumerate(rates):
        if not isinstance(tier, dict):
            raise ValueError(f"{label}.rates[{index}] must be an object")
        threshold = number(tier.get("min_balance", 0), f"{label}.rates[{index}].min_balance")
        apy = number(tier.get("apy_percent"), f"{label}.rates[{index}].apy_percent")
        if threshold <= deposit:
            eligible.append((threshold, apy))
    if not eligible:
        return None
    return max(eligible, key=lambda item: item[0])


def account_minimum(account, card_name):
    opening = number(account.get("opening_minimum", 0), f"{account['name']}.opening_minimum")
    ongoing = number(account.get("ongoing_minimum", 0), f"{account['name']}.ongoing_minimum")
    override = account.get("required_card_for_balance_override")
    required_card = None
    if override is not None:
        if not isinstance(override, dict) or not override.get("card"):
            raise ValueError(f"{account['name']}.required_card_for_balance_override is invalid")
        required_card = str(override["card"])
        if card_name == required_card:
            ongoing = number(override.get("ongoing_minimum"), f"{account['name']}.override.ongoing_minimum")
    return opening, ongoing, required_card


def candidate(account, card, deposit, years):
    name = str(account.get("name", ""))
    if not name:
        raise ValueError("Each savings account needs a name")
    card_name = None if card is None else str(card.get("name", ""))
    if card is not None and not card_name:
        raise ValueError("Each card needs a name")

    opening_min, ongoing_min, required_card = account_minimum(account, card_name)
    tier = choose_rate(account.get("rates"), deposit, name)
    feasible = deposit >= opening_min and deposit >= ongoing_min and tier is not None
    missing = []
    status = "confirmed"
    if required_card and card_name != required_card:
        feasible = False
        missing.append(f"requires active {required_card} for the stated balance override")
    if card is not None:
        card_status = card.get("eligibility_status", "conditional")
        if card_status not in {"confirmed", "conditional", "ineligible"}:
            raise ValueError(f"{card_name}.eligibility_status is invalid")
        if card_status == "ineligible":
            feasible = False
            status = "ineligible"
        elif card_status == "conditional" and status == "confirmed":
            status = "conditional"
        missing.extend(str(x) for x in card.get("missing_conditions", []))

    if not feasible and status == "confirmed":
        status = "infeasible"
    if tier is None:
        base_apy = Decimal("0")
        tier_threshold = None
    else:
        tier_threshold, base_apy = tier

    card_bonus = Decimal("0")
    if card_name is not None:
        bonuses = account.get("card_bonuses", {})
        if not isinstance(bonuses, dict):
            raise ValueError(f"{name}.card_bonuses must be an object")
        if card_name in bonuses:
            card_bonus = number(bonuses[card_name], f"{name}.card_bonuses[{card_name}]")
    other_bonus = number(account.get("other_confirmed_bonus_percent", 0), f"{name}.other_confirmed_bonus_percent")
    checking_bonus = number(account.get("linked_checking_boost_percent", 0), f"{name}.linked_checking_boost_percent")
    total_apy = base_apy + card_bonus + other_bonus + checking_bonus
    gross = deposit * ((Decimal("1") + total_apy / Decimal("100")) ** years - Decimal("1"))
    fee = Decimal("0") if card is None else number(card.get("annual_fee", 0), f"{card_name}.annual_fee") * years

    return {
        "savings_account": name,
        "card": card_name,
        "status": status,
        "feasible_at_deposit": feasible,
        "opening_minimum": money(opening_min),
        "ongoing_minimum": money(ongoing_min),
        "selected_tier_minimum": None if tier_threshold is None else money(tier_threshold),
        "base_apy_percent": str(base_apy),
        "card_bonus_percent": str(card_bonus),
        "other_confirmed_bonus_percent": str(other_bonus),
        "linked_checking_boost_percent": str(checking_bonus),
        "total_apy_percent": str(total_apy),
        "estimated_gross_interest": money(gross),
        "annual_card_fee_over_term": money(fee),
        "estimated_net_benefit": money(gross - fee),
        "missing_conditions": missing,
    }


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    deposit = number(payload.get("deposit_amount"), "deposit_amount")
    years = number(payload.get("term_years", 1), "term_years")
    if deposit < 0 or years <= 0:
        raise ValueError("deposit_amount must be nonnegative and term_years must be positive")
    accounts = payload.get("savings_accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("savings_accounts must be a nonempty array")
    cards = payload.get("cards", [])
    if not isinstance(cards, list):
        raise ValueError("cards must be an array")

    results = []
    for account in accounts:
        if not isinstance(account, dict):
            raise ValueError("Each savings account must be an object")
        results.append(candidate(account, None, deposit, years))
        for card in cards:
            if not isinstance(card, dict):
                raise ValueError("Each card must be an object")
            results.append(candidate(account, card, deposit, years))

    def ordering(item):
        usable = item["status"] in {"confirmed", "conditional"} and item["feasible_at_deposit"]
        confirmed = item["status"] == "confirmed"
        return (usable, confirmed, Decimal(item["estimated_net_benefit"]), Decimal(item["estimated_gross_interest"]))

    results.sort(key=ordering, reverse=True)
    print(json.dumps({
        "deposit_amount": money(deposit),
        "term_years": str(years),
        "ranking": results,
        "note": "Estimates use supplied APYs as effective annual rates. Confirm eligibility, current disclosures, and unprovided costs before acting."
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
