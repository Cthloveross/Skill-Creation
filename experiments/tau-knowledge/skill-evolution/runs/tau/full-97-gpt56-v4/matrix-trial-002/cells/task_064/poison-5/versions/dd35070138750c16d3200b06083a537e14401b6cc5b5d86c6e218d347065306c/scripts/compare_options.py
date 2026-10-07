#!/usr/bin/env python3
"""Rank documented savings/card combinations from JSON stdin.

Input and output schemas are documented in SKILL.md.  This program performs no
banking action and deliberately relies only on values supplied at runtime.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("0.01")


def number(value, field, required=True):
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def money(value):
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def display_decimal(value):
    # Preserve a JSON number while avoiding Decimal serialization issues.
    return float(value)


def evaluate(option, balance, withdrawals, avoid_score):
    name = f"{option.get('savings_account', '')} + {option.get('card', '')}".strip(" +")
    reasons = []
    base = number(option.get("base_apy_percent"), "base_apy_percent")
    bonus = number(option.get("card_apy_bonus_percent", 0), "card_apy_bonus_percent")
    annual_fee = number(option.get("annual_card_fee", 0), "annual_card_fee")
    opening = number(option.get("opening_deposit_minimum"), "opening_deposit_minimum", False)
    ongoing = number(option.get("ongoing_minimum_balance"), "ongoing_minimum_balance", False)
    limit = number(option.get("monthly_withdrawal_limit"), "monthly_withdrawal_limit", False)

    if opening is None:
        reasons.append("opening deposit minimum is unknown")
    elif balance < opening:
        reasons.append("balance is below the opening deposit minimum")
    if ongoing is None:
        reasons.append("ongoing minimum balance is unknown")
    elif balance < ongoing:
        reasons.append("balance is below the ongoing minimum")
    if limit is None:
        reasons.append("monthly withdrawal limit is unknown")
    elif limit >= 0 and withdrawals > limit:
        reasons.append("expected withdrawals exceed the monthly withdrawal limit")
    if avoid_score and bool(option.get("credit_score_required", False)):
        reasons.append("customer requested no credit-score-dependent recommendation")

    effective = base + bonus
    interest = balance * effective / Decimal("100")
    net = interest - annual_fee
    feasible = not reasons
    return {
        "combination": name,
        "savings_account": option.get("savings_account"),
        "card": option.get("card"),
        "feasible": feasible,
        "effective_apy_percent": display_decimal(effective),
        "estimated_interest": display_decimal(money(interest)),
        "annual_card_fee": display_decimal(money(annual_fee)),
        "net_one_year_value": display_decimal(money(net)),
        "net_one_year_value_unrounded": str(net),
        "reasons": reasons,
        "notes": option.get("notes", []),
        "ongoing_minimum_balance": None if ongoing is None else display_decimal(ongoing),
        "monthly_withdrawal_limit": None if limit is None else display_decimal(limit),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        balance = number(payload.get("balance"), "balance")
        withdrawals = number(payload.get("monthly_withdrawals"), "monthly_withdrawals")
        if balance < 0 or withdrawals < 0:
            raise ValueError("balance and monthly_withdrawals cannot be negative")
        options = payload.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError("options must be a nonempty list")
        avoid_score = bool(payload.get("avoid_credit_score_requirement", False))
        evaluated = [evaluate(x, balance, withdrawals, avoid_score) for x in options]
        feasible = [x for x in evaluated if x["feasible"]]
        feasible.sort(key=lambda x: Decimal(x["net_one_year_value_unrounded"]), reverse=True)
        ineligible = [x for x in evaluated if not x["feasible"]]
        for row in evaluated:
            row.pop("net_one_year_value_unrounded", None)
        print(json.dumps({
            "balance": display_decimal(balance),
            "monthly_withdrawals": display_decimal(withdrawals),
            "ranked_options": feasible,
            "feasible_options": feasible,
            "ineligible_options": ineligible,
        }, indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
