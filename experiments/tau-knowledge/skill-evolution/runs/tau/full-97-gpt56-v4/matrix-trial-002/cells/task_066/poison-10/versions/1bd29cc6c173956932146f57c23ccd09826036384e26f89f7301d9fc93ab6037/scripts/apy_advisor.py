#!/usr/bin/env python3
"""Calculate documented effective savings APY configurations from JSON stdin.

The program is intentionally read-only: it has no network, customer, or banking-action
interfaces.  APY fields are percentage points, e.g. 0.45 means +0.45 percentage points.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, not boolean")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def clean_decimal(value):
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def choose_base(account, balance):
    tiers = account.get("tiers")
    if tiers is None:
        return number(account["base_apy"], "base_apy"), None
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be a nonempty list when supplied")
    eligible = []
    for index, tier in enumerate(tiers):
        threshold = number(tier["minimum_balance"], f"tiers[{index}].minimum_balance")
        rate = number(tier["apy"], f"tiers[{index}].apy")
        if threshold <= balance:
            eligible.append((threshold, rate))
    if not eligible:
        raise ValueError("no APY tier applies at the supplied balance")
    threshold, rate = max(eligible, key=lambda item: item[0])
    return rate, threshold


def highest(entries, label):
    if not entries:
        return Decimal("0"), []
    max_rate = max(item["apy"] for item in entries)
    winners = [item for item in entries if item["apy"] == max_rate]
    return max_rate, winners


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be an object")
    balance = number(payload["balance"], "balance")
    if balance < 0:
        raise ValueError("balance cannot be negative")
    accounts = payload.get("savings_accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("savings_accounts must be a nonempty list")
    boosts = payload.get("checking_boosts", [])
    cards = payload.get("card_bonuses", [])
    if not isinstance(boosts, list) or not isinstance(cards, list):
        raise ValueError("checking_boosts and card_bonuses must be lists")

    normalized_boosts = []
    for index, item in enumerate(boosts):
        normalized_boosts.append({
            "savings_id": item["savings_id"],
            "checking_name": item["checking_name"],
            "apy": number(item["apy"], f"checking_boosts[{index}].apy"),
        })
    normalized_cards = []
    for index, item in enumerate(cards):
        normalized_cards.append({
            "savings_id": item["savings_id"],
            "card_name": item["card_name"],
            "apy": number(item["apy"], f"card_bonuses[{index}].apy"),
            "eligibility_note": item.get("eligibility_note", "eligibility must be verified"),
        })

    warnings = [
        "Results are maxima only among supplied records. They do not establish customer eligibility, approval, ownership, linkage, or ongoing good standing.",
        "One highest card bonus and one highest checking boost are used; bonuses within either category are not stacked.",
    ]
    excluded = []
    configurations = []
    seen_ids = set()

    for index, account in enumerate(accounts):
        account_id = account["id"]
        name = account["name"]
        if account_id in seen_ids:
            raise ValueError(f"duplicate savings account id: {account_id}")
        seen_ids.add(account_id)
        minimum = number(account.get("minimum_balance", 0), f"savings_accounts[{index}].minimum_balance")
        if minimum > balance:
            excluded.append({
                "savings_id": account_id,
                "name": name,
                "minimum_balance": clean_decimal(minimum),
                "reason": "stated balance is below documented ongoing minimum balance",
            })
            continue
        base_rate, tier_threshold = choose_base(account, balance)
        account_boosts = [b for b in normalized_boosts if b["savings_id"] == account_id]
        account_cards = [c for c in normalized_cards if c["savings_id"] == account_id]
        checking_rate, checking_winners = highest(account_boosts, "checking")
        card_rate, card_winners = highest(account_cards, "card")
        relationship = account.get("relationship_bonus")
        relationship_rate = Decimal("0")
        if relationship is not None:
            if not isinstance(relationship, dict):
                raise ValueError("relationship_bonus must be an object")
            if relationship.get("qualifies") is True:
                relationship_rate = number(relationship.get("apy", 0), "relationship_bonus.apy")
            else:
                warnings.append(f"Relationship bonus for {name} was not included because qualification was not true.")
        total = base_rate + checking_rate + card_rate + relationship_rate
        configurations.append({
            "savings_id": account_id,
            "savings_name": name,
            "base_apy": clean_decimal(base_rate),
            "applicable_tier_minimum_balance": None if tier_threshold is None else clean_decimal(tier_threshold),
            "checking_boost_apy": clean_decimal(checking_rate),
            "selected_checking_accounts": [x["checking_name"] for x in checking_winners],
            "card_bonus_apy": clean_decimal(card_rate),
            "selected_cards": [x["card_name"] for x in card_winners],
            "card_eligibility_notes": [x["eligibility_note"] for x in card_winners],
            "relationship_bonus_apy": clean_decimal(relationship_rate),
            "effective_apy": clean_decimal(total),
        })

    best = None
    if configurations:
        best_value = max(Decimal(item["effective_apy"]) for item in configurations)
        best = clean_decimal(best_value)
        best_configs = [item for item in configurations if Decimal(item["effective_apy"]) == best_value]
    else:
        best_configs = []
        warnings.append("No supplied savings account can meet its documented ongoing minimum at the stated balance.")

    return {
        "balance": clean_decimal(balance),
        "eligible_configurations": configurations,
        "best_effective_apy": best,
        "best_configurations": best_configs,
        "excluded_accounts": excluded,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
