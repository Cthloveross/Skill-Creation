#!/usr/bin/env python3
"""Select Gold Savings APY components and calculate daily-compounded interest.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the public input/output schema. Monetary outputs are rounded to cents only at
period end; intermediate accrual retains full floating-point precision.
"""

import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(2)


def number(value, name, nonnegative=True):
    if isinstance(value, bool):
        fail(f"{name} must be a number, not a boolean")
    try:
        result = float(value)
    except (TypeError, ValueError):
        fail(f"{name} must be numeric")
    if not math.isfinite(result):
        fail(f"{name} must be finite")
    if nonnegative and result < 0:
        fail(f"{name} must not be negative")
    return result


def number_list(value, name):
    if value is None:
        return []
    if not isinstance(value, list):
        fail(f"{name} must be an array")
    return [number(item, f"{name}[{index}]") for index, item in enumerate(value)]


def daily_rate(apy_pct):
    return (1.0 + apy_pct / 100.0) ** (1.0 / 365.0) - 1.0


def compounded_interest(balances, apy_pct):
    """Accrue daily on each day's supplied balance plus prior unpaid accrual."""
    accrual = 0.0
    rate = daily_rate(apy_pct)
    for balance in balances:
        accrual += (balance + accrual) * rate
    return accrual


def money(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def implied_apy(balances, actual_interest):
    """Solve annual effective APY that produces actual_interest for the balances."""
    if actual_interest == 0:
        return 0.0
    low, high = 0.0, 1000.0
    while compounded_interest(balances, high) < actual_interest and high < 1_000_000:
        high *= 2.0
    if compounded_interest(balances, high) < actual_interest:
        return None
    for _ in range(100):
        mid = (low + high) / 2.0
        if compounded_interest(balances, mid) < actual_interest:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def main(data):
    if not isinstance(data, dict):
        fail("input must be a JSON object")
    if "base_apy_pct" not in data:
        fail("base_apy_pct is required")

    base = number(data["base_apy_pct"], "base_apy_pct")
    checking = number_list(data.get("checking_boosts_pct", []), "checking_boosts_pct")
    cards = number_list(data.get("card_bonuses_pct", []), "card_bonuses_pct")
    selected_checking = max(checking) if checking else 0.0
    selected_card = max(cards) if cards else 0.0
    expected_apy = base + selected_checking + selected_card

    output = {
        "ok": True,
        "base_apy_pct": base,
        "selected_checking_boost_pct": selected_checking,
        "selected_card_bonus_pct": selected_card,
        "expected_apy_pct": expected_apy,
        "checking_boosts_stack": False,
        "card_bonuses_stack": False,
        "checking_and_card_components_stack": True,
    }

    balances_provided = "daily_balances" in data and data["daily_balances"] is not None
    balances = number_list(data.get("daily_balances"), "daily_balances") if balances_provided else []
    if balances_provided and not balances:
        fail("daily_balances must contain every day in the reviewed period")

    actual_provided = "actual_interest" in data and data["actual_interest"] is not None
    actual_interest = number(data["actual_interest"], "actual_interest") if actual_provided else None
    displayed_rate_provided = "actual_apy_pct" in data and data["actual_apy_pct"] is not None

    if displayed_rate_provided:
        output["actual_apy_pct"] = number(data["actual_apy_pct"], "actual_apy_pct")
        output["actual_apy_source"] = "provided_displayed_rate"

    if balances:
        raw_expected = compounded_interest(balances, expected_apy)
        output["days_calculated"] = len(balances)
        output["expected_interest"] = money(raw_expected)
        output["expected_interest_unrounded"] = raw_expected
        output["daily_balance_coverage_required"] = "Caller must confirm these balances cover the complete statement period."

    if actual_provided:
        output["actual_interest"] = money(actual_interest)

    if balances and actual_provided:
        difference = money(money(compounded_interest(balances, expected_apy)) - money(actual_interest))
        output["amount_difference"] = difference
        output["positive_discrepancy"] = difference > 0
        output["correction_ready_only_if_period_verified"] = difference > 0
        if not displayed_rate_provided:
            inferred = implied_apy(balances, actual_interest)
            if inferred is not None:
                output["actual_apy_pct"] = inferred
                output["actual_apy_source"] = "inferred_from_complete_daily_balances_and_posted_interest"

    print(json.dumps(output, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
    main(payload)
