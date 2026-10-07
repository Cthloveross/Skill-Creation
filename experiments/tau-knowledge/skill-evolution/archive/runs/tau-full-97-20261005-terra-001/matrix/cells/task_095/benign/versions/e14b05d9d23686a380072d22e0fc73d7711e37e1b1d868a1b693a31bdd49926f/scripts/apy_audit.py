#!/usr/bin/env python3
"""Deterministically calculate an APY component selection and monthly interest estimate.

Reads one JSON object from stdin and writes one JSON result object to stdout.
See SKILL.md for the public input schema and balance semantics.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from typing import Any

getcontext().prec = 40
ZERO = Decimal("0")
ONE = Decimal("1")
CENT = Decimal("0.01")


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def decimal_value(value: Any, field: str, nonnegative: bool = True) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if nonnegative and result < ZERO:
        raise ValueError(f"{field} must not be negative")
    return result


def bonus_list(value: Any, field: str) -> list[tuple[str, Decimal]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    parsed: list[tuple[str, Decimal]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{field}[{index}].name must be a nonempty string")
        applicable = item.get("applicable", True)
        if not isinstance(applicable, bool):
            raise ValueError(f"{field}[{index}].applicable must be boolean")
        apy = decimal_value(item.get("apy"), f"{field}[{index}].apy")
        if applicable:
            parsed.append((name, apy))
    return parsed


def highest(items: list[tuple[str, Decimal]]) -> tuple[Decimal, list[str]]:
    if not items:
        return ZERO, []
    value = max(apy for _, apy in items)
    return value, sorted(name for name, apy in items if apy == value)


def dtext(value: Decimal) -> str:
    # Fixed point avoids lossy JSON floating-point output.
    return format(value, "f")


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
    if not isinstance(raw, dict):
        fail("input must be a JSON object")

    try:
        base_apy = decimal_value(raw.get("base_apy"), "base_apy")
        cards = bonus_list(raw.get("card_bonuses", []), "card_bonuses")
        checking = bonus_list(raw.get("checking_bonuses", []), "checking_bonuses")
        relationship = bonus_list(raw.get("relationship_bonuses", []), "relationship_bonuses")
        card_apy, card_names = highest(cards)
        checking_apy, checking_names = highest(checking)
        relationship_apy = sum((apy for _, apy in relationship), ZERO)
        total_apy = base_apy + card_apy + checking_apy + relationship_apy

        result: dict[str, Any] = {
            "ok": True,
            "base_apy": dtext(base_apy),
            "selected_card_bonus": {
                "apy": dtext(card_apy),
                "names": card_names,
            },
            "selected_checking_bonus": {
                "apy": dtext(checking_apy),
                "names": checking_names,
            },
            "relationship_bonus": {
                "apy": dtext(relationship_apy),
                "names": sorted(name for name, _ in relationship),
            },
            "total_expected_apy": dtext(total_apy),
        }

        has_constant = "constant_balance" in raw and raw["constant_balance"] is not None
        has_daily = "daily_opening_balances" in raw and raw["daily_opening_balances"] is not None
        if has_constant and has_daily:
            raise ValueError("provide exactly one of constant_balance or daily_opening_balances")
        if not has_constant and not has_daily:
            if "actual_interest" in raw and raw["actual_interest"] is not None:
                raise ValueError("balance data and period_days are required to compare actual_interest")
            print(json.dumps(result, sort_keys=True))
            return

        period_days_raw = raw.get("period_days")
        if isinstance(period_days_raw, bool):
            raise ValueError("period_days must be a positive integer")
        try:
            period_days = int(period_days_raw)
        except (TypeError, ValueError):
            raise ValueError("period_days must be a positive integer")
        if str(period_days) != str(period_days_raw).strip() and not isinstance(period_days_raw, int):
            raise ValueError("period_days must be a positive integer")
        if period_days < 1 or period_days > 366:
            raise ValueError("period_days must be between 1 and 366")

        days_in_year_raw = raw.get("days_in_year", 365)
        if isinstance(days_in_year_raw, bool):
            raise ValueError("days_in_year must be a positive integer")
        try:
            days_in_year = int(days_in_year_raw)
        except (TypeError, ValueError):
            raise ValueError("days_in_year must be a positive integer")
        if days_in_year < 1:
            raise ValueError("days_in_year must be a positive integer")

        if has_constant:
            balance = decimal_value(raw["constant_balance"], "constant_balance")
            balances = [balance] * period_days
            method = "constant_balance"
        else:
            supplied = raw["daily_opening_balances"]
            if not isinstance(supplied, list):
                raise ValueError("daily_opening_balances must be an array")
            if len(supplied) != period_days:
                raise ValueError("daily_opening_balances length must equal period_days")
            balances = [decimal_value(v, f"daily_opening_balances[{i}]") for i, v in enumerate(supplied)]
            method = "daily_opening_balances"

        daily_rate = (ONE + total_apy / Decimal("100")) ** (ONE / Decimal(days_in_year)) - ONE
        accrued = ZERO
        for balance in balances:
            accrued = (balance + accrued) * daily_rate + accrued
        rounded = accrued.quantize(CENT, rounding=ROUND_HALF_UP)
        result.update({
            "interest_method": method,
            "period_days": period_days,
            "days_in_year": days_in_year,
            "daily_rate": dtext(daily_rate),
            "expected_interest_unrounded": dtext(accrued),
            "expected_interest_rounded": dtext(rounded),
        })

        if "actual_interest" in raw and raw["actual_interest"] is not None:
            actual = decimal_value(raw["actual_interest"], "actual_interest")
            actual_rounded = actual.quantize(CENT, rounding=ROUND_HALF_UP)
            difference = (rounded - actual_rounded).quantize(CENT, rounding=ROUND_HALF_UP)
            result.update({
                "actual_interest_rounded": dtext(actual_rounded),
                "amount_difference": dtext(difference),
                "shortfall_verified_by_inputs": difference > ZERO,
            })

        print(json.dumps(result, sort_keys=True))
    except ValueError as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
