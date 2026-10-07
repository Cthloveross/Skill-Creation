#!/usr/bin/env python3
"""Compare savings/card pairings.

Reads one JSON object from stdin using the schema in SKILL.md and writes exactly one
JSON object to stdout. Amounts are rounded to cents only in output calculations.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s must be numeric" % field)
    if not result.is_finite():
        raise ValueError("%s must be finite" % field)
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def number(value):
    # JSON numbers retain useful decimals while avoiding Decimal serialization.
    return float(value)


def required_object(value, field):
    if not isinstance(value, dict):
        raise ValueError("%s must be an object" % field)
    return value


def required_list(value, field):
    if not isinstance(value, list):
        raise ValueError("%s must be a list" % field)
    return value


def best_bonus(bonus_candidates):
    """Return the highest positive/zero bonus and its source; no stacking."""
    if not bonus_candidates:
        return ZERO, None
    # Stable tie handling uses the supplied order.
    source, value = max(bonus_candidates, key=lambda item: item[1])
    return value, source


def main(data):
    data = required_object(data, "input")
    deposit = dec(data.get("deposit"), "deposit")
    if deposit < ZERO:
        raise ValueError("deposit must not be negative")

    savings = required_list(data.get("savings_accounts"), "savings_accounts")
    cards = required_list(data.get("cards", []), "cards")
    held_cards = required_list(data.get("held_cards", []), "held_cards")
    checking = required_list(data.get("checking_accounts", []), "checking_accounts")
    include_none = data.get("include_no_new_card", True)
    if not isinstance(include_none, bool):
        raise ValueError("include_no_new_card must be boolean")

    card_choices = []
    if include_none:
        card_choices.append({"name": None, "annual_fee": ZERO, "eligible": True,
                             "eligibility_notes": [], "bonuses_pct_by_savings": {}})
    for index, card in enumerate(cards):
        card = required_object(card, "cards[%d]" % index)
        if not isinstance(card.get("name"), str) or not card["name"].strip():
            raise ValueError("cards[%d].name must be a nonempty string" % index)
        eligible = card.get("eligible")
        if not isinstance(eligible, bool):
            raise ValueError("cards[%d].eligible must be boolean" % index)
        card_choices.append({
            "name": card["name"],
            "annual_fee": dec(card.get("annual_fee", 0), "cards[%d].annual_fee" % index),
            "eligible": eligible,
            "eligibility_notes": required_list(card.get("eligibility_notes", []), "cards[%d].eligibility_notes" % index),
            "bonuses_pct_by_savings": required_object(card.get("bonuses_pct_by_savings", {}), "cards[%d].bonuses_pct_by_savings" % index),
        })

    parsed_held = []
    for index, card in enumerate(held_cards):
        card = required_object(card, "held_cards[%d]" % index)
        if not isinstance(card.get("name"), str) or not card["name"].strip():
            raise ValueError("held_cards[%d].name must be a nonempty string" % index)
        if not isinstance(card.get("eligible"), bool):
            raise ValueError("held_cards[%d].eligible must be boolean" % index)
        parsed_held.append(card)

    options = []
    for s_index, account in enumerate(savings):
        account = required_object(account, "savings_accounts[%d]" % s_index)
        name = account.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("savings_accounts[%d].name must be a nonempty string" % s_index)
        base = dec(account.get("base_apy_pct"), "%s.base_apy_pct" % name)
        minimum = dec(account.get("minimum_balance", 0), "%s.minimum_balance" % name)
        monthly_fee = dec(account.get("monthly_fee_below_min", 0), "%s.monthly_fee_below_min" % name)
        other = dec(account.get("other_additive_bonus_pct", 0), "%s.other_additive_bonus_pct" % name)
        if minimum < ZERO or monthly_fee < ZERO:
            raise ValueError("minimum balance and monthly fee must not be negative")
        boost_map = required_object(account.get("checking_boosts_pct", {}), "%s.checking_boosts_pct" % name)
        boosts = [(check, dec(boost_map[check], "%s checking boost" % name))
                  for check in checking if check in boost_map]
        checking_bonus, checking_source = best_bonus(boosts)
        below_minimum = deposit < minimum
        annual_account_fees = monthly_fee * Decimal(12) if below_minimum else ZERO

        for choice in card_choices:
            bonus_candidates = []
            for held in parsed_held:
                if held["eligible"]:
                    mapping = required_object(held.get("bonuses_pct_by_savings", {}), "held card bonus mapping")
                    if name in mapping:
                        bonus_candidates.append((held["name"], dec(mapping[name], "held card bonus")))
            if choice["name"] is not None and choice["eligible"] and name in choice["bonuses_pct_by_savings"]:
                bonus_candidates.append((choice["name"], dec(choice["bonuses_pct_by_savings"][name], "card bonus")))
            card_bonus, card_source = best_bonus(bonus_candidates)
            effective = base + card_bonus + checking_bonus + other
            gross = deposit * effective / Decimal(100)
            annual_card_fee = choice["annual_fee"]
            net = gross - annual_card_fee - annual_account_fees
            conditions = list(account.get("requirements", []))
            known_eligible = choice["eligible"]
            if choice["name"] is not None and not choice["eligible"]:
                conditions.extend(choice["eligibility_notes"])
                if not choice["eligibility_notes"]:
                    conditions.append("Card eligibility is unresolved.")
            if below_minimum:
                conditions.append("Deposit is below the stated ongoing minimum; stated monthly fee included.")
            options.append({
                "savings_account": name,
                "new_card": choice["name"],
                "known_eligible": known_eligible,
                "base_apy_pct": number(base),
                "selected_card_bonus": ({"source": card_source, "apy_bonus_pct": number(card_bonus)} if card_source else None),
                "selected_checking_boost": ({"source": checking_source, "apy_bonus_pct": number(checking_bonus)} if checking_source else None),
                "other_additive_bonus_pct": number(other),
                "effective_apy_pct": number(effective),
                "gross_interest": number(money(gross)),
                "annual_card_fee": number(money(annual_card_fee)),
                "annual_account_fees": number(money(annual_account_fees)),
                "net_one_year_value": number(money(net)),
                "conditions": conditions,
            })

    options.sort(key=lambda x: (not x["known_eligible"], -x["net_one_year_value"]))
    best = next((item for item in options if item["known_eligible"]), None)
    return {"valid": True, "assumption": "Deposit remains constant for one year; APY is already annual.",
            "ranked_options": options, "best_known_option": best}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), separators=(",", ":"), ensure_ascii=False))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, separators=(",", ":")))
