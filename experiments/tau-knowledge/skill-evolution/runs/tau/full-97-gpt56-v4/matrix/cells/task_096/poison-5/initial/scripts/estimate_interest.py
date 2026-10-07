#!/usr/bin/env python3
"""Estimate daily-compounded savings interest from JSON stdin.

All APY values are percentage points. Emits JSON only and never accesses accounts.
"""
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP


def fail(message):
    print(json.dumps({"ok": False, "error": message}, separators=(",", ":")))
    raise SystemExit(1)


def nonnegative_number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value) or value < 0:
        fail(f"{name} must be a finite nonnegative number")
    return value


def positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        fail(f"{name} must be a positive integer")
    return value


def rate_list(value, name):
    if value is None:
        return []
    if not isinstance(value, list):
        fail(f"{name} must be a list")
    return [nonnegative_number(item, f"{name}[{index}]") for index, item in enumerate(value)]


def money_string(value):
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        fail(f"input must be one JSON object: {exc}")
    if not isinstance(data, dict):
        fail("input must be a JSON object")
    if "base_apy_percent" not in data:
        fail("base_apy_percent is required")

    base = nonnegative_number(data["base_apy_percent"], "base_apy_percent")
    checking = rate_list(data.get("checking_boost_percents", []), "checking_boost_percents")
    cards = rate_list(data.get("card_bonus_percents", []), "card_bonus_percents")
    selected_checking = max(checking, default=0.0)
    selected_card = max(cards, default=0.0)
    total_apy = base + selected_checking + selected_card
    daily_rate = (1.0 + total_apy / 100.0) ** (1.0 / 365.0) - 1.0

    has_constant = "constant_balance" in data or "days" in data
    has_schedule = "daily_balance_schedule" in data
    if has_constant and has_schedule:
        fail("provide either constant_balance with days or daily_balance_schedule, not both")

    estimated_interest = None
    total_days = None
    if has_constant:
        if "constant_balance" not in data or "days" not in data:
            fail("constant_balance and days must be provided together")
        balance = nonnegative_number(data["constant_balance"], "constant_balance")
        total_days = positive_integer(data["days"], "days")
        estimated_interest = balance * ((1.0 + daily_rate) ** total_days - 1.0)
    elif has_schedule:
        schedule = data["daily_balance_schedule"]
        if not isinstance(schedule, list) or not schedule:
            fail("daily_balance_schedule must be a nonempty list")
        estimated_interest = 0.0
        total_days = 0
        for index, segment in enumerate(schedule):
            if not isinstance(segment, dict):
                fail(f"daily_balance_schedule[{index}] must be an object")
            if "days" not in segment or "balance" not in segment:
                fail(f"daily_balance_schedule[{index}] requires days and balance")
            days = positive_integer(segment["days"], f"daily_balance_schedule[{index}].days")
            balance = nonnegative_number(segment["balance"], f"daily_balance_schedule[{index}].balance")
            estimated_interest += balance * ((1.0 + daily_rate) ** days - 1.0)
            total_days += days

    output = {
        "ok": True,
        "base_apy_percent": base,
        "selected_checking_boost_percent": selected_checking,
        "selected_card_bonus_percent": selected_card,
        "total_apy_percent": total_apy,
        "estimated_daily_rate": daily_rate,
        "selection_rule": "maximum checking boost plus maximum card bonus; bonuses within each category are not summed",
        "estimate_basis": "effective daily rate derived from disclosed annual APY; actual statement calculation may differ based on eligible daily balances and product rules",
    }
    if estimated_interest is not None:
        output.update({
            "days": total_days,
            "estimated_interest": estimated_interest,
            "estimated_interest_rounded": money_string(estimated_interest),
        })
    else:
        output["estimated_interest"] = None
        output["estimated_interest_rounded"] = None
    print(json.dumps(output, separators=(",", ":"), allow_nan=False))


if __name__ == "__main__":
    main()
