#!/usr/bin/env python3
"""Compare savings/card net yield from JSON stdin; no banking side effects."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def number(value, field, allow_negative=False):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not value.is_finite() or (value < ZERO and not allow_negative):
        raise ValueError(f"{field} must be a finite {'number' if allow_negative else 'nonnegative number'}")
    return value


def obj(value, field):
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def strings(value, field):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{field} must be an array of strings")
    return value


def rendered_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def rendered_number(value):
    return format(value, "f")


def highest_checking_boost(account, checking_accounts):
    boosts = obj(account.get("checking_boosts_percent", {}), "checking_boosts_percent")
    matching = [(name, number(boosts[name], "checking boost"))
                for name in checking_accounts if name in boosts]
    if not matching:
        return ZERO, []
    highest = max(boost for _, boost in matching)
    return highest, [name for name, boost in matching if boost == highest]


def parse_cards(raw_cards, require_card):
    if not isinstance(raw_cards, list):
        raise ValueError("cards must be an array")
    if require_card and not raw_cards:
        raise ValueError("cards must be nonempty when require_card is true")
    cards = []
    for i, raw in enumerate(raw_cards):
        raw = obj(raw, f"cards[{i}]")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"cards[{i}].name must be a nonempty string")
        status = raw.get("eligibility_status", "unknown")
        if status not in ("confirmed", "unknown", "ineligible"):
            raise ValueError("eligibility_status must be confirmed, unknown, or ineligible")
        cards.append({"name": name, "status": status,
                      "fee": number(raw.get("annual_fee", 0), "annual_fee"),
                      "conditions": strings(raw.get("conditions", []), "conditions")})
    if not require_card:
        cards.append({"name": None, "status": "confirmed", "fee": ZERO, "conditions": []})
    return cards


def main(payload):
    payload = obj(payload, "input")
    deposit = number(payload.get("deposit"), "deposit")
    checking = strings(payload.get("active_checking_accounts", []), "active_checking_accounts")
    require_card = payload.get("require_card", True)
    if not isinstance(require_card, bool):
        raise ValueError("require_card must be boolean")
    requested_withdrawals = payload.get("required_monthly_withdrawals")
    if requested_withdrawals is not None:
        requested_withdrawals = number(requested_withdrawals, "required_monthly_withdrawals")
        if requested_withdrawals != requested_withdrawals.to_integral_value():
            raise ValueError("required_monthly_withdrawals must be a whole number")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty array")
    cards = parse_cards(payload.get("cards", []), require_card)
    results, rejected = [], []

    for i, raw in enumerate(accounts):
        account = obj(raw, f"accounts[{i}]")
        name = account.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"accounts[{i}].name must be a nonempty string")
        base = number(account.get("base_apy_percent"), "base_apy_percent")
        opening = number(account.get("opening_minimum", 0), "opening_minimum")
        ongoing = number(account.get("ongoing_minimum", 0), "ongoing_minimum")
        account_cost = number(account.get("annual_account_cost", 0), "annual_account_cost")
        other = number(account.get("other_additive_bonus_percent", 0), "other_additive_bonus_percent")
        bonuses = obj(account.get("card_bonuses_percent", {}), "card_bonuses_percent")
        reasons = []
        if deposit < opening:
            reasons.append("deposit is below opening minimum")
        if deposit < ongoing:
            reasons.append("deposit is below ongoing minimum")
        limit = account.get("monthly_withdrawal_limit")
        if limit is not None:
            limit = number(limit, "monthly_withdrawal_limit", allow_negative=True)
            if limit < -1 or limit != limit.to_integral_value():
                raise ValueError("monthly_withdrawal_limit must be -1 or a nonnegative whole number")
            if requested_withdrawals is not None and limit != -1 and requested_withdrawals > limit:
                reasons.append("monthly withdrawal limit is below requested withdrawals")
        if reasons:
            rejected.append({"account": name, "feasible": False, "reasons": reasons,
                             "deposit": rendered_money(deposit), "opening_minimum": rendered_money(opening),
                             "ongoing_minimum": rendered_money(ongoing), "monthly_withdrawal_limit": None if limit is None else int(limit)})
            continue
        checking_bonus, selected_checking = highest_checking_boost(account, checking)
        for card in cards:
            if card["status"] == "ineligible":
                continue
            card_bonus = ZERO if card["name"] is None else number(bonuses.get(card["name"], 0), "card bonus")
            effective = base + checking_bonus + other + card_bonus
            interest = deposit * effective / Decimal("100")
            costs = account_cost + card["fee"]
            net = interest - costs
            results.append({"account": name, "card": card["name"], "feasible": True,
                            "conditional": card["status"] == "unknown", "conditions": card["conditions"],
                            "base_apy_percent": rendered_number(base), "card_bonus_percent": rendered_number(card_bonus),
                            "checking_bonus_percent": rendered_number(checking_bonus),
                            "selected_checking_accounts": selected_checking,
                            "other_additive_bonus_percent": rendered_number(other),
                            "effective_apy_percent": rendered_number(effective),
                            "estimated_interest": rendered_money(interest),
                            "annual_account_cost": rendered_money(account_cost),
                            "card_annual_fee": rendered_money(card["fee"]),
                            "annual_costs": rendered_money(costs), "net_one_year": rendered_money(net),
                            "monthly_withdrawal_limit": None if limit is None else int(limit)})
    results.sort(key=lambda x: (Decimal(x["net_one_year"]), not x["conditional"], Decimal(x["effective_apy_percent"])), reverse=True)
    return {"method": "constant balance × effective APY, minus disclosed annual costs",
            "deposit": rendered_money(deposit), "selected": results[0] if results else None,
            "ranked_options": results, "rejected_accounts": rejected,
            "notice": "Conditional selections require eligibility confirmation and are not approvals. This calculation has no banking side effects."}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
