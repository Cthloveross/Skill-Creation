#!/usr/bin/env python3
"""Compute a documented monthly savings-interest discrepancy.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the evidence-derived input schema.  Monetary values may be JSON
numbers or decimal strings. APYs are percentage values (for example, 4.5).
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 48
ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")
DAYS_YEAR = Decimal("365")
CENT = Decimal("0.01")


def dec(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal number")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")


def decimal_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    values = [dec(item, field) for item in value]
    if any(item < ZERO for item in values):
        raise ValueError(f"{field} cannot contain negative values")
    return values


def daily_rate(apy):
    # APY is an annual yield. This finds the daily rate whose 365-day
    # compounding produces that yield.
    return (ONE + apy / HUNDRED) ** (ONE / DAYS_YEAR) - ONE


def period_interest(balances, apy):
    """Accrue daily on each day's principal plus prior accrued interest."""
    accrued = ZERO
    rate = daily_rate(apy)
    for balance in balances:
        accrued += (balance + accrued) * rate
    return accrued


def infer_apy(balances, target_interest):
    """Solve the nonnegative APY that produces target_interest."""
    if target_interest == ZERO:
        return ZERO
    if not balances or max(balances) == ZERO:
        raise ValueError("cannot derive actual APY from zero balances and positive interest")
    low = ZERO
    high = Decimal("1")
    # Expand safely until the target is bracketed.
    while period_interest(balances, high) < target_interest:
        high *= Decimal("2")
        if high > Decimal("100000"):
            raise ValueError("actual interest cannot be bracketed with a plausible APY")
    for _ in range(160):
        middle = (low + high) / Decimal("2")
        if period_interest(balances, middle) < target_interest:
            low = middle
        else:
            high = middle
    return (low + high) / Decimal("2")


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def text_decimal(value, places=None):
    if places is not None:
        value = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return format(value, "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balances = decimal_list(payload.get("daily_principal_balances"), "daily_principal_balances")
    if not balances:
        raise ValueError("daily_principal_balances must contain at least one day")

    expected = payload.get("expected")
    if not isinstance(expected, dict):
        raise ValueError("expected must be an object")
    base = dec(expected.get("base_or_tier_apy"), "expected.base_or_tier_apy")
    if base < ZERO:
        raise ValueError("expected.base_or_tier_apy cannot be negative")
    checking = decimal_list(expected.get("checking_boosts", []), "expected.checking_boosts")
    cards = decimal_list(expected.get("card_bonuses", []), "expected.card_bonuses")
    other = decimal_list(expected.get("other_additive_bonuses", []), "expected.other_additive_bonuses")

    selected_checking = max(checking) if checking else ZERO
    selected_card = max(cards) if cards else ZERO
    expected_apy = base + selected_checking + selected_card + sum(other, ZERO)
    expected_unrounded = period_interest(balances, expected_apy)
    expected_credit = money(expected_unrounded)

    blockers = []
    actual_credit = None
    actual_apy = None
    if "actual_interest_credit" not in payload:
        blockers.append("actual_interest_credit is required from a posted interest_credit transaction")
    else:
        actual_credit = dec(payload["actual_interest_credit"], "actual_interest_credit")
        if actual_credit < ZERO:
            blockers.append("actual_interest_credit cannot be negative")
        elif "actual_apy" in payload and payload["actual_apy"] is not None:
            actual_apy = dec(payload["actual_apy"], "actual_apy")
            if actual_apy < ZERO:
                blockers.append("actual_apy cannot be negative")
        else:
            actual_apy = infer_apy(balances, actual_credit)

    discrepancy = None
    correction = None
    if actual_credit is not None and actual_credit >= ZERO:
        discrepancy = money(expected_credit - money(actual_credit))
        correction = discrepancy if discrepancy > ZERO else ZERO
    if actual_apy is None:
        blockers.append("actual APY is required for the mandatory discrepancy report")

    return {
        "period_days": len(balances),
        "selected_checking_boost_apy": text_decimal(selected_checking),
        "selected_card_bonus_apy": text_decimal(selected_card),
        "expected_apy": text_decimal(expected_apy, "0.00000001"),
        "expected_interest_unrounded": text_decimal(expected_unrounded, "0.00000001"),
        "expected_interest_credit": text_decimal(expected_credit),
        "actual_interest_credit": None if actual_credit is None else text_decimal(money(actual_credit)),
        "actual_apy": None if actual_apy is None else text_decimal(actual_apy, "0.00000001"),
        "amount_difference": None if discrepancy is None else text_decimal(discrepancy),
        "correction_amount": None if correction is None else text_decimal(correction),
        "action_allowed": not blockers and correction is not None and correction > ZERO,
        "blockers": blockers,
        "notes": [
            "Use only verified period balances and documented active benefits.",
            "Checking and card lists are each reduced to their highest value; other bonuses are additive.",
            "A nonpositive correction amount must not be sent to the credit tool."
        ]
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
