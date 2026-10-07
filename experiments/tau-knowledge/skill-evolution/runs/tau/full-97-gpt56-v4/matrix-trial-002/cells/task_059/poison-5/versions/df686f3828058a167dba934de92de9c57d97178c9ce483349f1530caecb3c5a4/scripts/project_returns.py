#!/usr/bin/env python3
"""Project one-year savings and card economics from supplied, eligible terms.

Reads one JSON object from stdin and writes one JSON object to stdout. Decimal
strings are preferred to avoid binary floating-point rounding in money values.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value, field, errors, default=ZERO):
    if value is None:
        return default
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a decimal number")
        return default
    if not result.is_finite() or result < ZERO:
        errors.append(f"{field} must be a finite nonnegative number")
        return default
    return result


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def percent(value):
    # Keep enough precision to explain combined documented rates.
    return str(value.normalize()) if value != ZERO else "0"


def project_savings(candidate, index, errors):
    prefix = f"savings_candidates[{index}]"
    balance = decimal_value(candidate.get("balance"), f"{prefix}.balance", errors)
    base = decimal_value(candidate.get("base_apy_percent"), f"{prefix}.base_apy_percent", errors)
    checking = decimal_value(candidate.get("checking_bonus_apy_percent"), f"{prefix}.checking_bonus_apy_percent", errors)
    other = decimal_value(candidate.get("other_bonus_apy_percent"), f"{prefix}.other_bonus_apy_percent", errors)
    fees = decimal_value(candidate.get("annual_fees"), f"{prefix}.annual_fees", errors)
    raw_bonuses = candidate.get("card_bonus_apy_percents", [])
    if not isinstance(raw_bonuses, list):
        errors.append(f"{prefix}.card_bonus_apy_percents must be a list")
        raw_bonuses = []
    bonuses = [decimal_value(x, f"{prefix}.card_bonus_apy_percents[{i}]", errors) for i, x in enumerate(raw_bonuses)]
    mode = candidate.get("card_bonus_mode", "highest")
    if mode not in ("highest", "sum"):
        errors.append(f"{prefix}.card_bonus_mode must be highest or sum")
        mode = "highest"
    card_bonus = (max(bonuses) if bonuses else ZERO) if mode == "highest" else sum(bonuses, ZERO)
    applicable = base + checking + card_bonus + other
    interest = balance * applicable / Decimal("100")
    return {
        "id": candidate.get("id", f"savings-{index + 1}"),
        "balance": money(balance),
        "base_apy_percent": percent(base),
        "checking_bonus_apy_percent": percent(checking),
        "applied_card_bonus_apy_percent": percent(card_bonus),
        "other_bonus_apy_percent": percent(other),
        "applicable_apy_percent": percent(applicable),
        "projected_interest": money(interest),
        "annual_fees": money(fees),
        "net_return": money(interest - fees),
    }


def project_card(candidate, index, errors):
    prefix = f"card_candidates[{index}]"
    low = decimal_value(candidate.get("monthly_spend_low"), f"{prefix}.monthly_spend_low", errors)
    high = decimal_value(candidate.get("monthly_spend_high"), f"{prefix}.monthly_spend_high", errors)
    if high < low:
        errors.append(f"{prefix}.monthly_spend_high must be at least monthly_spend_low")
    rate = decimal_value(candidate.get("reward_rate_percent"), f"{prefix}.reward_rate_percent", errors)
    annual_fee = decimal_value(candidate.get("annual_fee"), f"{prefix}.annual_fee", errors)
    other_fees = decimal_value(candidate.get("expected_other_annual_fees"), f"{prefix}.expected_other_annual_fees", errors)
    fees = annual_fee + other_fees
    annual_low, annual_high = low * 12, high * 12
    rewards_low, rewards_high = annual_low * rate / Decimal("100"), annual_high * rate / Decimal("100")
    return {
        "id": candidate.get("id", f"card-{index + 1}"),
        "annual_spend_low": money(annual_low),
        "annual_spend_high": money(annual_high),
        "reward_rate_percent": percent(rate),
        "rewards_low": money(rewards_low),
        "rewards_high": money(rewards_high),
        "annual_fees": money(fees),
        "net_return_low": money(rewards_low - fees),
        "net_return_high": money(rewards_high - fees),
    }


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"invalid JSON: {exc.msg}"], "savings": [], "cards": []}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"errors": ["input must be a JSON object"], "savings": [], "cards": []}))
        return
    errors = []
    savings = data.get("savings_candidates", [])
    cards = data.get("card_candidates", [])
    if not isinstance(savings, list):
        errors.append("savings_candidates must be a list")
        savings = []
    if not isinstance(cards, list):
        errors.append("card_candidates must be a list")
        cards = []
    output = {
        "errors": errors,
        "savings": [project_savings(c, i, errors) if isinstance(c, dict) else None for i, c in enumerate(savings)],
        "cards": [project_card(c, i, errors) if isinstance(c, dict) else None for i, c in enumerate(cards)],
    }
    for group_name in ("savings", "cards"):
        cleaned = []
        for i, result in enumerate(output[group_name]):
            if result is None:
                errors.append(f"{group_name}_candidates[{i}] must be an object")
            else:
                cleaned.append(result)
        output[group_name] = cleaned
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
