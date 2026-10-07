#!/usr/bin/env python3
"""Select non-stacking APY bonuses and calculate period interest.

Reads one JSON object from stdin and writes one JSON object to stdout. APY inputs are
percentage points (for example, 5.5 represents 5.5%), not decimal fractions.
"""

import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40


def number(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def nonnegative_list(value, field):
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    result = []
    for index, item in enumerate(value):
        parsed = number(item, f"{field}[{index}]")
        if parsed < 0:
            raise ValueError(f"{field}[{index}] must not be negative")
        result.append(parsed)
    return result


def display(value, places=None):
    if places is not None:
        value = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return float(value)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    required = ("base_apy", "tier_eligible", "checking_boosts", "card_bonuses", "other_additive_bonuses")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))
    if payload["tier_eligible"] is not True:
        raise ValueError("tier is not confirmed eligible; supply the documented applicable base rate before calculation")

    base = number(payload["base_apy"], "base_apy")
    if base < 0:
        raise ValueError("base_apy must not be negative")
    checking = nonnegative_list(payload["checking_boosts"], "checking_boosts")
    cards = nonnegative_list(payload["card_bonuses"], "card_bonuses")
    other = nonnegative_list(payload["other_additive_bonuses"], "other_additive_bonuses")
    checking_selected = max(checking, default=Decimal("0"))
    card_selected = max(cards, default=Decimal("0"))
    expected_apy = base + checking_selected + card_selected + sum(other, Decimal("0"))

    result = {
        "selected_checking_boost": display(checking_selected),
        "selected_card_bonus": display(card_selected),
        "other_additive_bonus_total": display(sum(other, Decimal("0"))),
        "expected_apy": display(expected_apy),
        "interest_available": False,
        "calculation_basis": None,
    }

    balances = payload.get("daily_balances")
    if balances is not None:
        balances = nonnegative_list(balances, "daily_balances")
        if not balances:
            raise ValueError("daily_balances must contain at least one day")
        basis = "daily_balances"
    else:
        days = payload.get("period_days")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("period_days must be a positive integer when daily_balances is omitted")
        constant_balance = payload.get("constant_balance")
        if constant_balance is None:
            result["calculation_basis"] = "apy_only"
            return result
        balance = number(constant_balance, "constant_balance")
        if balance < 0:
            raise ValueError("constant_balance must not be negative")
        balances = [balance] * days
        basis = "constant_balance_estimate"

    daily_rate = expected_apy / Decimal("100") / Decimal("365")
    accrued = Decimal("0")
    for balance in balances:
        # Daily compounding: each day's accrual is based on the balance plus accrued interest.
        accrued = (balance + accrued) * daily_rate + accrued

    result.update({
        "interest_available": True,
        "calculation_basis": basis,
        "period_days_used": len(balances),
        "expected_interest": display(accrued, "0.01"),
    })
    if "actual_interest" in payload and payload["actual_interest"] is not None:
        actual = number(payload["actual_interest"], "actual_interest")
        result["actual_interest"] = display(actual, "0.01")
        result["difference"] = display(accrued - actual, "0.01")
    return result


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("expected one JSON object on stdin")
        print(json.dumps(main(json.loads(raw)), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
