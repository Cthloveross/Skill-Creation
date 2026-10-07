#!/usr/bin/env python3
"""Select non-stacking APY bonuses and calculate daily-compounded interest.

Reads a JSON object on stdin and writes a JSON object on stdout. It deliberately
accepts documented candidate rates from the caller rather than encoding any bank
product catalogue or customer data.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from typing import Any

getcontext().prec = 40
ZERO = Decimal("0")
ONE = Decimal("1")
DAYS_PER_YEAR = Decimal("365")


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def decimal_field(value: Any, name: str, *, nonnegative: bool = True) -> Decimal:
    if isinstance(value, bool) or value is None:
        fail(f"{name} must be a number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{name} must be a number")
    if not parsed.is_finite():
        fail(f"{name} must be finite")
    if nonnegative and parsed < ZERO:
        fail(f"{name} must not be negative")
    return parsed


def required_bool(item: dict[str, Any], key: str, label: str) -> bool:
    value = item.get(key)
    if not isinstance(value, bool):
        fail(f"{label}.{key} must be true or false")
    return value


def candidates(value: Any, kind: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        fail(f"{kind} must be an array")
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        label = f"{kind}[{index}]"
        if not isinstance(item, dict):
            fail(f"{label} must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            fail(f"{label}.name must be a nonempty string")
        cleaned.append(item)
    return cleaned


def select_card(items: list[dict[str, Any]]) -> tuple[Decimal, str | None]:
    valid: list[tuple[Decimal, str]] = []
    for index, item in enumerate(items):
        label = f"credit_card_candidates[{index}]"
        active = required_bool(item, "active", label)
        eligible = required_bool(item, "eligible", label)
        rate = decimal_field(item.get("apy_bonus_pct"), f"{label}.apy_bonus_pct")
        if active and eligible:
            valid.append((rate, item["name"]))
    if not valid:
        return ZERO, None
    # Stable deterministic tie-breaker by name after choosing the highest rate.
    rate, name = sorted(valid, key=lambda x: (-x[0], x[1]))[0]
    return rate, name


def select_checking(items: list[dict[str, Any]]) -> tuple[Decimal, str | None]:
    valid: list[tuple[Decimal, str]] = []
    for index, item in enumerate(items):
        label = f"checking_candidates[{index}]"
        active = required_bool(item, "active", label)
        linked = required_bool(item, "linked", label)
        qualifying = required_bool(item, "qualifying_pair", label)
        rate = decimal_field(item.get("apy_boost_pct"), f"{label}.apy_boost_pct")
        if active and linked and qualifying:
            valid.append((rate, item["name"]))
    if not valid:
        return ZERO, None
    rate, name = sorted(valid, key=lambda x: (-x[0], x[1]))[0]
    return rate, name


def parse_balances(value: Any) -> list[tuple[date, Decimal]]:
    if not isinstance(value, list) or not value:
        fail("daily_balances must be a nonempty array")
    parsed: list[tuple[date, Decimal]] = []
    seen: set[date] = set()
    for index, item in enumerate(value):
        label = f"daily_balances[{index}]"
        if not isinstance(item, dict):
            fail(f"{label} must be an object")
        raw_date = item.get("date")
        if not isinstance(raw_date, str):
            fail(f"{label}.date must be YYYY-MM-DD")
        try:
            day = date.fromisoformat(raw_date)
        except ValueError:
            fail(f"{label}.date must be YYYY-MM-DD")
        if day in seen:
            fail("daily_balances must not contain duplicate dates")
        seen.add(day)
        balance = decimal_field(item.get("principal_balance"), f"{label}.principal_balance")
        parsed.append((day, balance))
    parsed.sort(key=lambda pair: pair[0])
    for previous, current in zip(parsed, parsed[1:]):
        if current[0] != previous[0] + timedelta(days=1):
            fail("daily_balances dates must be consecutive calendar days")
    return parsed


def main(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        fail("input must be a JSON object")
    base = decimal_field(request.get("base_apy_pct"), "base_apy_pct")
    separate = decimal_field(request.get("separate_bonus_pct", 0), "separate_bonus_pct")
    card_rate, card_name = select_card(candidates(request.get("credit_card_candidates"), "credit_card_candidates"))
    checking_rate, checking_name = select_checking(candidates(request.get("checking_candidates"), "checking_candidates"))
    balances = parse_balances(request.get("daily_balances"))

    places = request.get("currency_places", 2)
    if isinstance(places, bool) or not isinstance(places, int) or places < 0 or places > 6:
        fail("currency_places must be an integer from 0 through 6")

    combined_apy = base + card_rate + checking_rate + separate
    daily_rate = (ONE + (combined_apy / Decimal("100"))) ** (ONE / DAYS_PER_YEAR) - ONE
    accrued = ZERO
    for _, principal in balances:
        # principal is the supplied day balance excluding the as-yet-unposted
        # interest; accrued interest is included for daily compounding.
        accrued = accrued + (principal + accrued) * daily_rate

    quantum = ONE.scaleb(-places)
    expected_rounded = accrued.quantize(quantum, rounding=ROUND_HALF_UP)
    result: dict[str, Any] = {
        "ok": True,
        "selected_credit_card": card_name,
        "selected_credit_card_bonus_pct": str(card_rate),
        "selected_checking_account": checking_name,
        "selected_checking_boost_pct": str(checking_rate),
        "base_apy_pct": str(base),
        "separate_bonus_pct": str(separate),
        "expected_apy_pct": str(combined_apy),
        "daily_rate": str(daily_rate),
        "accrual_days": len(balances),
        "expected_interest_unrounded": str(accrued),
        "expected_interest": str(expected_rounded),
    }
    if "actual_interest" in request:
        actual = decimal_field(request["actual_interest"], "actual_interest")
        difference = accrued - actual
        difference_rounded = difference.quantize(quantum, rounding=ROUND_HALF_UP)
        result.update({
            "actual_interest": str(actual),
            "difference_expected_minus_actual": str(difference_rounded),
            "positive_undercredit_established": difference_rounded > ZERO,
            "recommended_credit_amount": str(difference_rounded) if difference_rounded > ZERO else None,
        })
    else:
        result["positive_undercredit_established"] = False
        result["recommended_credit_amount"] = None
        result["note"] = "Actual posted interest was not supplied; no discrepancy amount is established."
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
    print(json.dumps(main(payload), sort_keys=True))
