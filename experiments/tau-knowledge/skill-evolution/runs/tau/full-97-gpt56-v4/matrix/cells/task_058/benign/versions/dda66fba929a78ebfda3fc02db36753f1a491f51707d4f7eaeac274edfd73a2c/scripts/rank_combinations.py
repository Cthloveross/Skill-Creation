#!/usr/bin/env python3
"""Rank known-eligible card/savings pairs from a JSON request on stdin.

See SKILL.md for the public input and output schema.  This program is pure:
it performs no network, file, or banking operations beyond stdin/stdout.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
TWELVE = Decimal("12")
CENT = Decimal("0.01")


def fail(message):
    raise ValueError(message)


def number(value, label, minimum=None):
    if isinstance(value, bool) or value is None:
        fail(f"{label} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{label} must be a number")
    if not result.is_finite():
        fail(f"{label} must be finite")
    if minimum is not None and result < minimum:
        fail(f"{label} must be at least {minimum}")
    return result


def require_object(value, label):
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    return value


def require_list(value, label):
    if not isinstance(value, list):
        fail(f"{label} must be an array")
    return value


def require_name(item, label):
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        fail(f"{label}.name must be a nonempty string")
    return name


def as_money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def display_decimal(value):
    """JSON numeric output, preserving simple values while avoiding Decimal."""
    return float(value)


def parse_savings(raw):
    entries = []
    names = set()
    for i, item in enumerate(require_list(raw, "savings_accounts")):
        item = require_object(item, f"savings_accounts[{i}]")
        name = require_name(item, f"savings_accounts[{i}]")
        if name in names:
            fail(f"duplicate savings account name: {name}")
        names.add(name)
        if not isinstance(item.get("known_eligible"), bool):
            fail(f"savings_accounts[{i}].known_eligible must be boolean")
        entries.append({
            "name": name,
            "base_apy": number(item.get("base_apy_percent"), f"{name}.base_apy_percent"),
            "minimum": number(item.get("minimum_balance"), f"{name}.minimum_balance", ZERO),
            "eligible": item["known_eligible"],
            "fixed_bonus": number(item.get("fixed_apy_bonus_percent", 0), f"{name}.fixed_apy_bonus_percent"),
            "checking_bonus": number(item.get("checking_apy_bonus_percent", 0), f"{name}.checking_apy_bonus_percent"),
        })
    if not entries:
        fail("savings_accounts must not be empty")
    return entries


def parse_cards(raw):
    entries = []
    names = set()
    for i, item in enumerate(require_list(raw, "cards")):
        item = require_object(item, f"cards[{i}]")
        name = require_name(item, f"cards[{i}]")
        if name in names:
            fail(f"duplicate card name: {name}")
        names.add(name)
        if not isinstance(item.get("known_eligible"), bool):
            fail(f"cards[{i}].known_eligible must be boolean")
        reward = require_object(item.get("ordinary_reward"), f"{name}.ordinary_reward")
        reward_type = reward.get("type")
        if reward_type not in ("cashback_percent", "points_per_dollar"):
            fail(f"{name}.ordinary_reward.type must be cashback_percent or points_per_dollar")
        rate = number(reward.get("rate"), f"{name}.ordinary_reward.rate", ZERO)
        point_value = None
        if reward_type == "points_per_dollar":
            point_value = number(reward.get("point_value"), f"{name}.ordinary_reward.point_value", ZERO)
        entries.append({
            "name": name,
            "fee": number(item.get("annual_fee"), f"{name}.annual_fee", ZERO),
            "eligible": item["known_eligible"],
            "reward_type": reward_type,
            "reward_rate": rate,
            "point_value": point_value,
        })
    if not entries:
        fail("cards must not be empty")
    return entries


def bonus_for(lookup, savings_name, card_name):
    if lookup is None:
        return ZERO
    if not isinstance(lookup, dict):
        fail("card_apy_bonus_percent must be an object")
    row = lookup.get(savings_name, {})
    if not isinstance(row, dict):
        fail(f"card_apy_bonus_percent[{savings_name!r}] must be an object")
    return number(row.get(card_name, 0), f"card APY bonus for {card_name} / {savings_name}")


def reward_value(card, annual_spend):
    if card["reward_type"] == "cashback_percent":
        return annual_spend * card["reward_rate"] / HUNDRED
    return annual_spend * card["reward_rate"] * card["point_value"]


def main(request):
    request = require_object(request, "request")
    principal = number(request.get("principal"), "principal", ZERO)
    spend = require_object(request.get("monthly_spend"), "monthly_spend")
    monthly_low = number(spend.get("low"), "monthly_spend.low", ZERO)
    monthly_high = number(spend.get("high"), "monthly_spend.high", ZERO)
    if monthly_high < monthly_low:
        fail("monthly_spend.high must be greater than or equal to monthly_spend.low")
    annual_low = monthly_low * TWELVE
    annual_high = monthly_high * TWELVE
    savings = parse_savings(request.get("savings_accounts"))
    cards = parse_cards(request.get("cards"))
    bonus_lookup = request.get("card_apy_bonus_percent", {})

    warnings = []
    feasible_savings = []
    for account in savings:
        if not account["eligible"]:
            warnings.append(f"Excluded savings account with eligibility not established: {account['name']}")
        elif principal < account["minimum"]:
            warnings.append(f"Excluded savings account because principal is below its maintained-balance requirement: {account['name']}")
        else:
            feasible_savings.append(account)
    eligible_cards = []
    for card in cards:
        if not card["eligible"]:
            warnings.append(f"Excluded card with eligibility not established: {card['name']}")
        else:
            eligible_cards.append(card)
    if not feasible_savings:
        fail("no feasible savings account remains after eligibility and minimum-balance checks")
    if not eligible_cards:
        fail("no known-eligible card remains after eligibility checks")

    combinations = []
    for account in feasible_savings:
        for card in eligible_cards:
            card_bonus = bonus_for(bonus_lookup, account["name"], card["name"])
            effective_apy = account["base_apy"] + account["fixed_bonus"] + account["checking_bonus"] + card_bonus
            interest = principal * effective_apy / HUNDRED
            rewards_low = reward_value(card, annual_low)
            rewards_high = reward_value(card, annual_high)
            net_low = interest + rewards_low - card["fee"]
            net_high = interest + rewards_high - card["fee"]
            combinations.append({
                "savings_account": account["name"],
                "card": card["name"],
                "effective_apy_percent": display_decimal(effective_apy),
                "annual_interest": display_decimal(as_money(interest)),
                "ordinary_rewards_low": display_decimal(as_money(rewards_low)),
                "ordinary_rewards_high": display_decimal(as_money(rewards_high)),
                "annual_fee": display_decimal(as_money(card["fee"])),
                "net_return_low": display_decimal(as_money(net_low)),
                "net_return_high": display_decimal(as_money(net_high)),
            })
    combinations.sort(key=lambda row: (-row["net_return_low"], -row["net_return_high"], row["savings_account"], row["card"]))
    result = {
        "assumptions": {
            "principal_held_for_full_year": display_decimal(principal),
            "annual_spend_low": display_decimal(annual_low),
            "annual_spend_high": display_decimal(annual_high),
            "ranking_basis": "net_return_low (conservative lower end of stated monthly spending range)"
        },
        "recommendation": combinations[0],
        "eligible_combinations": combinations,
        "warnings": warnings,
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), allow_nan=False))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")), file=sys.stdout)
        sys.exit(2)
