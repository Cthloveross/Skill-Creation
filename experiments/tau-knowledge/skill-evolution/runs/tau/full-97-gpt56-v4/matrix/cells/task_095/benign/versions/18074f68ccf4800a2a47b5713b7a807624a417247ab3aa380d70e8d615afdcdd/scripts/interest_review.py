#!/usr/bin/env python3
"""Select non-stacking APY benefits and calculate daily-compounded interest.

Read one JSON object on stdin and emit one JSON object on stdout. Candidate
rates and balances are caller-supplied: this helper contains no product catalogue,
customer identifier, or bank-action logic.
"""
from __future__ import annotations
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from typing import Any

getcontext().prec = 40
ZERO, ONE, HUNDRED, DAYS_PER_YEAR = Decimal("0"), Decimal("1"), Decimal("100"), Decimal("365")


def fail(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def decimal_field(value: Any, name: str, *, nonnegative: bool = True) -> Decimal:
    if value is None or isinstance(value, bool):
        fail(f"{name} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{name} must be a number")
    if not result.is_finite():
        fail(f"{name} must be finite")
    if nonnegative and result < ZERO:
        fail(f"{name} must not be negative")
    return result


def bool_field(item: dict[str, Any], key: str, label: str) -> bool:
    result = item.get(key)
    if not isinstance(result, bool):
        fail(f"{label}.{key} must be true or false")
    return result


def candidate_list(value: Any, kind: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        fail(f"{kind} must be an array")
    result: list[dict[str, Any]] = []
    for i, item in enumerate(value):
        label = f"{kind}[{i}]"
        if not isinstance(item, dict):
            fail(f"{label} must be an object")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            fail(f"{label}.name must be a nonempty string")
        result.append(item)
    return result


def select_card(items: list[dict[str, Any]]) -> tuple[Decimal, str | None]:
    choices: list[tuple[Decimal, str]] = []
    for i, item in enumerate(items):
        label = f"credit_card_candidates[{i}]"
        eligible = bool_field(item, "active", label) and bool_field(item, "eligible", label)
        rate = decimal_field(item.get("apy_bonus_pct"), f"{label}.apy_bonus_pct")
        if eligible:
            choices.append((rate, item["name"]))
    return min(choices, key=lambda x: (-x[0], x[1])) if choices else (ZERO, None)


def select_checking(items: list[dict[str, Any]]) -> tuple[Decimal, str | None]:
    choices: list[tuple[Decimal, str]] = []
    for i, item in enumerate(items):
        label = f"checking_candidates[{i}]"
        eligible = (bool_field(item, "active", label)
                    and bool_field(item, "linked", label)
                    and bool_field(item, "qualifying_pair", label))
        rate = decimal_field(item.get("apy_boost_pct"), f"{label}.apy_boost_pct")
        if eligible:
            choices.append((rate, item["name"]))
    return min(choices, key=lambda x: (-x[0], x[1])) if choices else (ZERO, None)


def parse_iso(raw: Any, label: str) -> date:
    if not isinstance(raw, str):
        fail(f"{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(raw)
    except ValueError:
        fail(f"{label} must be YYYY-MM-DD")


def balances_from_request(request: dict[str, Any]) -> list[tuple[date, Decimal]]:
    """Use detailed daily balances, or a documented constant-balance interval."""
    supplied = request.get("daily_balances")
    has_constant = any(k in request for k in ("constant_principal_balance", "period_start", "period_end"))
    if supplied is not None and has_constant:
        fail("provide daily_balances or a constant-balance period, not both")
    if supplied is not None:
        if not isinstance(supplied, list) or not supplied:
            fail("daily_balances must be a nonempty array")
        rows: list[tuple[date, Decimal]] = []
        seen: set[date] = set()
        for i, item in enumerate(supplied):
            label = f"daily_balances[{i}]"
            if not isinstance(item, dict):
                fail(f"{label} must be an object")
            day = parse_iso(item.get("date"), f"{label}.date")
            if day in seen:
                fail("daily_balances must not contain duplicate dates")
            seen.add(day)
            rows.append((day, decimal_field(item.get("principal_balance"), f"{label}.principal_balance")))
        rows.sort(key=lambda pair: pair[0])
        for previous, current in zip(rows, rows[1:]):
            if current[0] != previous[0] + timedelta(days=1):
                fail("daily_balances dates must be consecutive calendar days")
        return rows
    principal = decimal_field(request.get("constant_principal_balance"), "constant_principal_balance")
    first = parse_iso(request.get("period_start"), "period_start")
    last = parse_iso(request.get("period_end"), "period_end")
    if last < first:
        fail("period_end must not precede period_start")
    return [(first + timedelta(days=i), principal) for i in range((last - first).days + 1)]


def main(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        fail("input must be a JSON object")
    base = decimal_field(request.get("base_apy_pct"), "base_apy_pct")
    separate = decimal_field(request.get("separate_bonus_pct", 0), "separate_bonus_pct")
    card_rate, card_name = select_card(candidate_list(request.get("credit_card_candidates"), "credit_card_candidates"))
    checking_rate, checking_name = select_checking(candidate_list(request.get("checking_candidates"), "checking_candidates"))
    rows = balances_from_request(request)
    places = request.get("currency_places", 2)
    if isinstance(places, bool) or not isinstance(places, int) or not 0 <= places <= 6:
        fail("currency_places must be an integer from 0 through 6")

    apy = base + card_rate + checking_rate + separate
    daily_rate = (ONE + apy / HUNDRED) ** (ONE / DAYS_PER_YEAR) - ONE
    accrued = ZERO
    for _, principal in rows:
        accrued += (principal + accrued) * daily_rate
    quantum = ONE.scaleb(-places)
    expected = accrued.quantize(quantum, rounding=ROUND_HALF_UP)
    result: dict[str, Any] = {
        "ok": True, "selected_credit_card": card_name,
        "selected_credit_card_bonus_pct": str(card_rate),
        "selected_checking_account": checking_name,
        "selected_checking_boost_pct": str(checking_rate),
        "base_apy_pct": str(base), "separate_bonus_pct": str(separate),
        "expected_apy_pct": str(apy), "daily_rate": str(daily_rate),
        "accrual_days": len(rows), "expected_interest_unrounded": str(accrued),
        "expected_interest": str(expected),
    }
    if "actual_interest" in request:
        actual = decimal_field(request["actual_interest"], "actual_interest")
        difference = (accrued - actual).quantize(quantum, rounding=ROUND_HALF_UP)
        result.update({"actual_interest": str(actual), "difference_expected_minus_actual": str(difference),
                       "positive_undercredit_established": difference > ZERO,
                       "recommended_credit_amount": str(difference) if difference > ZERO else None})
    else:
        result.update({"positive_undercredit_established": False, "recommended_credit_amount": None,
                       "note": "Actual posted interest was not supplied; no discrepancy amount is established."})
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
    print(json.dumps(main(payload), sort_keys=True))
