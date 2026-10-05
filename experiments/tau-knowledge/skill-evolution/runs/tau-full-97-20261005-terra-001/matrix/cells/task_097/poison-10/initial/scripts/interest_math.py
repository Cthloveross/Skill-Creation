#!/usr/bin/env python3
"""Deterministic APY-component selection and daily-compounded interest math.

Read a JSON object from stdin and write exactly one JSON object to stdout.
See SKILL.md for the mode-specific input schemas.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
DAYS_PER_YEAR = Decimal("365")


def as_decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def decimal_text(value):
    return format(value, "f")


def nonnegative_list(values, field):
    if values is None:
        return []
    if not isinstance(values, list):
        raise ValueError(f"{field} must be a list")
    parsed = [as_decimal(v, field) for v in values]
    if any(v < 0 for v in parsed):
        raise ValueError(f"{field} cannot contain negative values")
    return parsed


def apy_mode(data):
    base = as_decimal(data.get("base_apy_percent"), "base_apy_percent")
    if base < 0:
        raise ValueError("base_apy_percent cannot be negative")
    cards = nonnegative_list(data.get("credit_card_bonus_percents", []), "credit_card_bonus_percents")
    checking = nonnegative_list(data.get("checking_boost_percents", []), "checking_boost_percents")
    other = nonnegative_list(data.get("other_additive_bonus_percents", []), "other_additive_bonus_percents")
    selected_card = max(cards) if cards else Decimal("0")
    selected_checking = max(checking) if checking else Decimal("0")
    expected = base + selected_card + selected_checking + sum(other, Decimal("0"))
    return {
        "ok": True,
        "mode": "apy",
        "expected_apy_percent": decimal_text(expected),
        "selected_credit_card_bonus_percent": decimal_text(selected_card),
        "selected_checking_boost_percent": decimal_text(selected_checking),
        "other_additive_bonus_total_percent": decimal_text(sum(other, Decimal("0"))),
    }


def daily_rate_from_apy(apy_percent):
    annual_factor = Decimal("1") + (apy_percent / Decimal("100"))
    if annual_factor <= 0:
        raise ValueError("apy_percent must be greater than -100")
    # APY is an annual yield, so derive the daily compounded periodic rate.
    return annual_factor.__pow__(Decimal("1") / DAYS_PER_YEAR) - Decimal("1")


def interest_mode(data):
    days = data.get("days")
    if not isinstance(days, list) or not days:
        raise ValueError("days must be a non-empty chronological list")
    accrued = Decimal("0")
    for index, day in enumerate(days):
        if not isinstance(day, dict):
            raise ValueError(f"days[{index}] must be an object")
        balance = as_decimal(day.get("end_of_day_principal_balance"),
                             f"days[{index}].end_of_day_principal_balance")
        apy = as_decimal(day.get("apy_percent"), f"days[{index}].apy_percent")
        if balance < 0:
            raise ValueError(f"days[{index}].end_of_day_principal_balance cannot be negative")
        rate = daily_rate_from_apy(apy)
        accrued = (balance + accrued) * rate + accrued

    expected_rounded = money(accrued)
    result = {
        "ok": True,
        "mode": "interest",
        "day_count": len(days),
        "expected_interest_unrounded": decimal_text(accrued),
        "expected_interest_rounded": decimal_text(expected_rounded),
    }
    if "actual_interest_credited" in data and data["actual_interest_credited"] is not None:
        actual = as_decimal(data["actual_interest_credited"], "actual_interest_credited")
        difference = money(expected_rounded - actual)
        result["actual_interest_credited"] = decimal_text(actual)
        result["difference_expected_minus_actual"] = decimal_text(difference)
        result["positive_difference_to_credit"] = decimal_text(difference) if difference > 0 else None
    return result


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        mode = data.get("mode")
        if mode == "apy":
            output = apy_mode(data)
        elif mode == "interest":
            output = interest_mode(data)
        else:
            raise ValueError("mode must be 'apy' or 'interest'")
    except Exception as exc:
        output = {"ok": False, "error": str(exc)}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
