#!/usr/bin/env python3
"""Calculate one-year savings/card comparison estimates from JSON stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

VALID_ELIGIBILITY = {"eligible", "unknown", "ineligible"}


def money(value):
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a number")
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def status_of(*statuses):
    if "ineligible" in statuses:
        return "ineligible"
    if "unknown" in statuses:
        return "unknown"
    return "eligible"


def spend_range(data):
    source = data.get("annual_spend")
    label = "annual_spend"
    multiplier = Decimal("1")
    if source is None:
        source = data.get("monthly_spend")
        label = "monthly_spend"
        multiplier = Decimal("12")
    if not isinstance(source, dict) or "min" not in source or "max" not in source:
        raise ValueError("provide annual_spend or monthly_spend with min and max")
    low = dec(source["min"], f"{label}.min") * multiplier
    high = dec(source["max"], f"{label}.max") * multiplier
    if low > high:
        raise ValueError(f"{label}.min must not exceed {label}.max")
    return low, high


def list_of_strings(value):
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def eligibility(item, label):
    value = item.get("eligibility", "unknown")
    if value not in VALID_ELIGIBILITY:
        raise ValueError(f"{label}.eligibility must be eligible, unknown, or ineligible")
    return value


def main(data):
    deposit = dec(data.get("deposit"), "deposit")
    spend_low, spend_high = spend_range(data)
    savings = data.get("savings_accounts")
    cards = data.get("cards")
    if not isinstance(savings, list) or not savings:
        raise ValueError("savings_accounts must be a nonempty list")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty list")

    boosts = data.get("linked_checking_boost_percent_by_savings", {})
    if not isinstance(boosts, dict):
        raise ValueError("linked_checking_boost_percent_by_savings must be an object")

    warnings = []
    comparisons = []
    for account in savings:
        if not isinstance(account, dict) or not account.get("name"):
            raise ValueError("each savings account needs a name")
        account_name = str(account["name"])
        base_apy = dec(account.get("base_apy_percent"), f"{account_name}.base_apy_percent")
        minimum_balance = dec(account.get("minimum_balance", 0), f"{account_name}.minimum_balance")
        opening_minimum = dec(account.get("required_opening_deposit", 0), f"{account_name}.required_opening_deposit")
        annual_savings_fee = dec(account.get("annual_fee", 0), f"{account_name}.annual_fee")
        account_status = eligibility(account, account_name)
        account_reasons = list_of_strings(account.get("requirements"))
        if deposit < opening_minimum:
            account_status = "ineligible"
            account_reasons.append("Deposit is below the documented opening-deposit requirement.")
        elif deposit < minimum_balance:
            account_status = "ineligible"
            account_reasons.append("Deposit is below the documented ongoing minimum balance.")
        checking_boost = dec(boosts.get(account_name, 0), f"linked boost for {account_name}")

        for card in cards:
            if not isinstance(card, dict) or not card.get("name"):
                raise ValueError("each card needs a name")
            card_name = str(card["name"])
            fee = dec(card.get("annual_fee", 0), f"{card_name}.annual_fee")
            reward_rate = dec(card.get("ordinary_reward_percent"), f"{card_name}.ordinary_reward_percent")
            card_status = eligibility(card, card_name)
            bonus_map = card.get("apy_bonus_percent_by_savings", {})
            if not isinstance(bonus_map, dict):
                raise ValueError(f"{card_name}.apy_bonus_percent_by_savings must be an object")
            card_bonus = dec(bonus_map.get(account_name, 0), f"APY bonus for {card_name}/{account_name}")
            effective_apy = base_apy + card_bonus + checking_boost
            interest = deposit * effective_apy / Decimal("100")
            rewards_low = spend_low * reward_rate / Decimal("100")
            rewards_high = spend_high * reward_rate / Decimal("100")
            net_low = interest + rewards_low - fee - annual_savings_fee
            net_high = interest + rewards_high - fee - annual_savings_fee
            reasons = account_reasons + list_of_strings(card.get("requirements"))
            combined_status = status_of(account_status, card_status)
            comparisons.append({
                "savings_account": account_name,
                "card": card_name,
                "eligibility": combined_status,
                "requirements_or_limitations": reasons,
                "effective_apy_percent": money(effective_apy),
                "components": {
                    "estimated_interest": money(interest),
                    "estimated_rewards_min": money(rewards_low),
                    "estimated_rewards_max": money(rewards_high),
                    "annual_card_fee": money(fee),
                    "annual_savings_fee": money(annual_savings_fee),
                    "card_apy_bonus_percent": money(card_bonus),
                    "linked_checking_boost_percent": money(checking_boost)
                },
                "net_one_year_value_min": money(net_low),
                "net_one_year_value_max": money(net_high)
            })

    rank = {"eligible": 0, "unknown": 1, "ineligible": 2}
    comparisons.sort(key=lambda row: (rank[row["eligibility"]], -row["net_one_year_value_min"], -row["net_one_year_value_max"]))
    return {
        "annual_spend": {"min": money(spend_low), "max": money(spend_high)},
        "assumptions": [
            "APY is treated as the stated one-year yield and is not compounded again.",
            "Rewards use the entered ordinary-purchase rate and assume eligible posted purchases with no returns.",
            "Only the supplied single-card APY bonus and supplied applicable checking boost are used."
        ],
        "input_warnings": warnings,
        "comparisons": comparisons
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level input must be an object")
        print(json.dumps(main(payload), indent=2, sort_keys=False))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
