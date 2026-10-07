#!/usr/bin/env python3
"""Evaluate documented savings/card net-yield scenarios from JSON stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, path, errors, default=None):
    if value is None:
        return default
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{path} must be numeric")
        return default
    if not result.is_finite():
        errors.append(f"{path} must be finite")
        return default
    return result


def money(value):
    return float(value.quantize(Decimal("0.00000001")))


def tier_rate(account, deposit, errors):
    tiers = account.get("apy_tiers")
    if tiers is not None:
        if not isinstance(tiers, list) or not tiers:
            errors.append(f"savings_accounts[{account.get('id', '?')}].apy_tiers must be a nonempty list")
            return None
        eligible = []
        for pos, tier in enumerate(tiers):
            if not isinstance(tier, dict):
                errors.append("each apy_tiers entry must be an object")
                continue
            floor = number(tier.get("minimum_balance"), f"apy_tiers[{pos}].minimum_balance", errors)
            rate = number(tier.get("apy_percent"), f"apy_tiers[{pos}].apy_percent", errors)
            if floor is not None and rate is not None and floor <= deposit:
                eligible.append((floor, rate))
        if not eligible:
            return None
        return max(eligible, key=lambda item: item[0])[1]
    return number(account.get("base_apy_percent"),
                  f"savings_accounts[{account.get('id', '?')}].base_apy_percent", errors)


def main(data):
    errors = []
    deposit = number(data.get("deposit"), "deposit", errors)
    if deposit is None or deposit <= 0:
        errors.append("deposit must be a positive number")
    savings = data.get("savings_accounts")
    cards = data.get("cards", [])
    boosts = data.get("checking_boosts", [])
    if not isinstance(savings, list) or not savings:
        errors.append("savings_accounts must be a nonempty list")
    if not isinstance(cards, list):
        errors.append("cards must be a list")
    if not isinstance(boosts, list):
        errors.append("checking_boosts must be a list")
    if errors:
        return {"results": [], "excluded": [], "errors": errors}

    require_card = data.get("require_card", True)
    if not isinstance(require_card, bool):
        return {"results": [], "excluded": [], "errors": ["require_card must be boolean"]}
    options = cards if require_card else [None] + cards
    if require_card and not cards:
        return {"results": [], "excluded": [], "errors": ["at least one card is required when require_card is true"]}

    results, excluded = [], []
    for account in savings:
        if not isinstance(account, dict) or not account.get("id") or not account.get("name"):
            errors.append("each savings account needs id and name")
            continue
        account_id = account["id"]
        opening = number(account.get("minimum_opening_deposit"), f"{account_id}.minimum_opening_deposit", errors, Decimal(0))
        ongoing = number(account.get("minimum_ongoing_balance"), f"{account_id}.minimum_ongoing_balance", errors, Decimal(0))
        rate = tier_rate(account, deposit, errors)
        if opening is None or ongoing is None or rate is None:
            excluded.append({"savings_id": account_id, "reason": "missing or unusable balance requirement or APY tier"})
            continue
        if deposit < opening or deposit < ongoing:
            excluded.append({"savings_id": account_id, "reason": "deposit does not meet documented opening or ongoing balance requirement"})
            continue

        noncard = []
        for bonus in account.get("additional_apy_bonuses", []):
            if isinstance(bonus, dict) and bonus.get("eligible") is True:
                amount = number(bonus.get("apy_percent"), "additional_apy_bonuses.apy_percent", errors)
                if amount is not None:
                    noncard.append((str(bonus.get("label", "qualified additional bonus")), amount))
        checking = []
        for boost in boosts:
            if isinstance(boost, dict) and boost.get("savings_id") == account_id and boost.get("eligible") is True:
                amount = number(boost.get("apy_percent"), "checking_boosts.apy_percent", errors)
                if amount is not None:
                    checking.append((str(boost.get("label", "qualified checking boost")), amount))

        for card in options:
            if card is not None and (not isinstance(card, dict) or not card.get("id") or not card.get("name")):
                errors.append("each card needs id and name")
                continue
            if card is not None and card.get("eligible_to_apply") is False:
                excluded.append({"savings_id": account_id, "card_id": card.get("id"), "reason": "documented application eligibility is not met"})
                continue
            fee = Decimal(0) if card is None else number(card.get("annual_fee"), f"{card.get('id')}.annual_fee", errors, Decimal(0))
            if fee is None:
                continue
            card_bonus = Decimal(0)
            if card is not None:
                raw = card.get("bonus_apy_percent_by_savings", {}).get(account_id, 0)
                card_bonus = number(raw, f"{card.get('id')}.bonus_apy_percent_by_savings.{account_id}", errors, Decimal(0))
                if card_bonus is None:
                    continue
            components = [{"label": "base APY at selected balance tier", "apy_percent": money(rate)}]
            for label, amount in noncard + checking:
                components.append({"label": label, "apy_percent": money(amount)})
            if card is not None and card_bonus != 0:
                components.append({"label": f"{card['name']} card APY bonus", "apy_percent": money(card_bonus)})
            total_rate = rate + sum((x[1] for x in noncard + checking), Decimal(0)) + card_bonus
            interest = deposit * total_rate / Decimal(100)
            conditional = card is not None and card.get("eligible_to_apply") is not True
            results.append({
                "savings_id": account_id,
                "savings_name": account["name"],
                "card_id": None if card is None else card["id"],
                "card_name": None if card is None else card["name"],
                "status": "conditional" if conditional else "eligible",
                "application_conditions": [] if card is None else card.get("application_conditions", []),
                "apy_components": components,
                "total_apy_percent": money(total_rate),
                "annual_interest_estimate": money(interest),
                "annual_card_fee": money(fee),
                "net_one_year_estimate": money(interest - fee),
                "assumption": "Deposit remains constant for one year; APY is applied as an annual yield."
            })
    results.sort(key=lambda r: (r["net_one_year_estimate"], r["total_apy_percent"]), reverse=True)
    return {"results": results, "excluded": excluded, "errors": errors}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"results": [], "excluded": [], "errors": [str(exc)]}))
