#!/usr/bin/env python3
"""Compute a savings-interest discrepancy from verified runtime inputs.

Reads one JSON object from stdin and writes one JSON object to stdout.
No banking tools are called by this program.
"""

import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def decimal_list(value, field):
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    values = [decimal_value(item, field) for item in value]
    if any(item < ZERO for item in values):
        raise ValueError(f"{field} cannot contain negative values")
    return values


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_json_number(value):
    # Strings avoid binary floating-point changes to monetary outputs.
    return format(value, "f")


def main(payload):
    required = ["base_apy", "actual_interest", "accrual_method"]
    missing = [name for name in required if name not in payload]
    if missing:
        raise ValueError("missing required field(s): " + ", ".join(missing))

    base_apy = decimal_value(payload["base_apy"], "base_apy")
    if base_apy < ZERO:
        raise ValueError("base_apy cannot be negative")
    actual_interest = decimal_value(payload["actual_interest"], "actual_interest")
    if actual_interest < ZERO:
        raise ValueError("actual_interest cannot be negative")

    checking = decimal_list(payload.get("checking_boosts", []), "checking_boosts")
    cards = decimal_list(payload.get("credit_card_bonuses", []), "credit_card_bonuses")
    relationships = decimal_list(payload.get("relationship_bonuses", []), "relationship_bonuses")
    tiers = decimal_list(payload.get("tier_bonuses", []), "tier_bonuses")

    # Empty lists represent no verified qualifying boost in that category.
    selected_checking = max(checking) if checking else ZERO
    selected_card = max(cards) if cards else ZERO
    expected_apy = base_apy + selected_checking + selected_card + sum(relationships, ZERO) + sum(tiers, ZERO)

    method = payload["accrual_method"]
    if method not in {"nominal_daily", "effective_apy_daily", "simple_period"}:
        raise ValueError("accrual_method must be nominal_daily, effective_apy_daily, or simple_period")

    assumptions = []
    if method in {"nominal_daily", "effective_apy_daily"}:
        balances = decimal_list(payload.get("daily_balances"), "daily_balances")
        if not balances:
            raise ValueError("daily_balances must contain at least one verified day for daily accrual")
        days_per_year = decimal_value(payload.get("days_per_year", 365), "days_per_year")
        if days_per_year <= ZERO:
            raise ValueError("days_per_year must be greater than zero")
        if method == "nominal_daily":
            rate = (expected_apy / HUNDRED) / days_per_year
            assumptions.append("Uses stated APY as a nominal annual rate divided by days_per_year.")
        else:
            # Decimal has no portable fractional exponent. Convert only this rate
            # calculation to float, then convert its string representation back.
            effective = float(expected_apy / HUNDRED)
            rate = Decimal(str(math.pow(1.0 + effective, 1.0 / float(days_per_year)) - 1.0))
            assumptions.append("Treats stated APY as an effective annual yield and derives a daily effective rate.")
        expected_interest = sum((balance * rate for balance in balances), ZERO)
        period_days = len(balances)
    else:
        average_balance = decimal_value(payload.get("average_balance"), "average_balance")
        if average_balance < ZERO:
            raise ValueError("average_balance cannot be negative")
        periods_per_year = decimal_value(payload.get("periods_per_year"), "periods_per_year")
        if periods_per_year <= ZERO:
            raise ValueError("periods_per_year must be greater than zero")
        expected_interest = average_balance * (expected_apy / HUNDRED) / periods_per_year
        period_days = None
        assumptions.append("Uses a simple-period calculation; only valid when that convention is documented.")

    expected_interest = money(expected_interest)
    actual_interest = money(actual_interest)
    difference = money(expected_interest - actual_interest)

    actual_apy = None
    actual_apy_valid = False
    if payload.get("actual_apy") is not None:
        actual_apy = decimal_value(payload["actual_apy"], "actual_apy")
        if actual_apy < ZERO:
            raise ValueError("actual_apy cannot be negative")
        actual_apy_valid = True

    validations = {
        "positive_discrepancy": difference > ZERO,
        "actual_apy_present": actual_apy_valid,
        "verified_period_and_balances_required": True,
        "documented_accrual_method_must_be_confirmed": True,
    }
    # This script cannot know whether runtime data was actually verified. The caller
    # must satisfy the last two flags outside the script before making a credit.
    can_credit = difference > ZERO
    report_ready = can_credit and actual_apy_valid

    return {
        "expected_apy": as_json_number(expected_apy),
        "selected_checking_boost": as_json_number(selected_checking),
        "selected_credit_card_bonus": as_json_number(selected_card),
        "relationship_bonus_total": as_json_number(sum(relationships, ZERO)),
        "tier_bonus_total": as_json_number(sum(tiers, ZERO)),
        "period_days": period_days,
        "expected_interest": as_json_number(expected_interest),
        "actual_interest": as_json_number(actual_interest),
        "amount_difference": as_json_number(difference),
        "actual_apy": as_json_number(actual_apy) if actual_apy_valid else None,
        "can_credit": can_credit,
        "report_ready": report_ready,
        "validations": validations,
        "assumptions": assumptions,
        "warning": "Only use a positive result after independently verifying account ownership, product eligibility, the posted interest transaction, all rate inputs, exact period balances, and the documented accrual convention.",
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin must contain one JSON object")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
