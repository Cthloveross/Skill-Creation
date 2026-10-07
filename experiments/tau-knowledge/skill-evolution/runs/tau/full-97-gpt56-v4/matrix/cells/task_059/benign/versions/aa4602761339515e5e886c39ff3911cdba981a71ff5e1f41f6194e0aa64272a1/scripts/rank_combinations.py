#!/usr/bin/env python3
"""Rank supplied savings/card scenarios. Reads one JSON object from stdin and writes JSON."""
import json
import sys


def money(value):
    return round(value + 0.0, 2)


def as_number(obj, key, default=0.0):
    value = obj.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    if value < 0:
        raise ValueError(f"{key} must be nonnegative")
    return float(value)


def evaluate(combo, balance, spend_low, spend_high):
    card_bonuses = combo.get("card_bonus_apy_pcts", [])
    if not isinstance(card_bonuses, list) or any(
        isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0
        for x in card_bonuses
    ):
        raise ValueError("card_bonus_apy_pcts must be an array of nonnegative numbers")

    base = as_number(combo, "base_apy_pct")
    checking = as_number(combo, "checking_bonus_apy_pct")
    relationship = as_number(combo, "relationship_bonus_apy_pct")
    card_bonus = max((float(x) for x in card_bonuses), default=0.0)
    effective_apy = base + checking + card_bonus + relationship
    annual_interest = balance * effective_apy / 100.0

    reward_low = as_number(combo, "reward_rate_low_pct")
    reward_high = as_number(combo, "reward_rate_high_pct")
    if reward_high < reward_low:
        raise ValueError("reward_rate_high_pct must be at least reward_rate_low_pct")
    rewards_low = spend_low * reward_low / 100.0
    rewards_high = spend_high * reward_high / 100.0

    signup_value = as_number(combo, "signup_bonus_value")
    signup_ok = combo.get("signup_bonus_eligible", False)
    if not isinstance(signup_ok, bool):
        raise ValueError("signup_bonus_eligible must be boolean")
    applied_signup = signup_value if signup_ok else 0.0
    account_fees = as_number(combo, "known_annual_account_fees")
    card_fee = as_number(combo, "card_annual_fee")
    fees = account_fees + card_fee
    value_low = annual_interest + rewards_low + applied_signup - fees
    value_high = annual_interest + rewards_high + applied_signup - fees

    return {
        "name": combo.get("name", "unnamed combination"),
        "eligible": combo.get("eligible", False),
        "eligibility_notes": combo.get("eligibility_notes", []),
        "base_apy_pct": base,
        "checking_bonus_apy_pct": checking,
        "highest_card_bonus_apy_pct": card_bonus,
        "relationship_bonus_apy_pct": relationship,
        "effective_apy_pct": effective_apy,
        "estimated_annual_interest": money(annual_interest),
        "estimated_rewards_low": money(rewards_low),
        "estimated_rewards_high": money(rewards_high),
        "applied_signup_bonus_value": money(applied_signup),
        "known_annual_fees": money(fees),
        "estimated_first_year_value_low": money(value_low),
        "estimated_first_year_value_high": money(value_high),
    }


def main():
    raw = json.load(sys.stdin)
    if not isinstance(raw, dict):
        raise ValueError("input must be a JSON object")
    balance = as_number(raw, "balance")
    spend_low = as_number(raw, "annual_spend_low")
    spend_high = as_number(raw, "annual_spend_high")
    if spend_high < spend_low:
        raise ValueError("annual_spend_high must be at least annual_spend_low")
    combos = raw.get("combinations")
    if not isinstance(combos, list) or not combos:
        raise ValueError("combinations must be a nonempty array")

    results = [evaluate(c, balance, spend_low, spend_high) for c in combos]
    ranked = sorted(
        results,
        key=lambda r: (not bool(r["eligible"]), -r["estimated_first_year_value_low"], -r["estimated_first_year_value_high"]),
    )
    output = {
        "assumptions": {
            "stable_balance_for_one_year": balance,
            "annual_spend_low": spend_low,
            "annual_spend_high": spend_high,
            "credit_card_bonus_rule": "highest supplied card APY bonus only",
            "amounts_are_pre_tax": True,
        },
        "ranked_combinations": ranked,
        "validation": {
            "input_valid": True,
            "excluded_or_conditional_combinations_require_human_review": [
                r["name"] for r in ranked if not r["eligible"]
            ],
        },
    }
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
