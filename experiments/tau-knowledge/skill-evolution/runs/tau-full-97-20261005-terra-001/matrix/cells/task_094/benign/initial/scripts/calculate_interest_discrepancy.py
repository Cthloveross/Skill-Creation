#!/usr/bin/env python3
"""Calculate a supported savings-interest correction from supplied evidence.

Reads one JSON object from stdin and emits one JSON object to stdout. No files,
network services, or bank actions are used.
"""

import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")


def fail(message):
    return {"status": "error", "error": message}


def decimal_number(value, field, nonnegative=True):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if nonnegative and result < 0:
        raise ValueError(f"{field} must be nonnegative")
    return result


def bonus_list(payload, field):
    value = payload.get(field, [])
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return [decimal_number(item, f"{field}[{index}]") for index, item in enumerate(value)]


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_json_number(value):
    # Decimal values are serialized as JSON numbers for banking tool compatibility.
    return float(value)


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")

    try:
        base = decimal_number(payload.get("base_apy"), "base_apy")
        checking = bonus_list(payload, "checking_boosts")
        cards = bonus_list(payload, "credit_card_bonuses")
        relationship = bonus_list(payload, "relationship_bonuses")
        tier = bonus_list(payload, "tier_bonuses")
        actual_interest = decimal_number(payload.get("actual_interest"), "actual_interest")

        days_in_year_raw = payload.get("days_in_year", 365)
        if isinstance(days_in_year_raw, bool) or not isinstance(days_in_year_raw, int) or days_in_year_raw <= 0:
            raise ValueError("days_in_year must be a positive integer")
        days_in_year = days_in_year_raw

        has_daily = "daily_balances" in payload
        has_constant = "constant_balance" in payload or "days" in payload
        if has_daily and has_constant:
            raise ValueError("provide daily_balances or constant_balance with days, not both")

        if has_daily:
            balances_raw = payload["daily_balances"]
            if not isinstance(balances_raw, list) or not balances_raw:
                raise ValueError("daily_balances must be a nonempty array")
            balances = [decimal_number(item, f"daily_balances[{index}]") for index, item in enumerate(balances_raw)]
            day_count = len(balances)
        else:
            balance = decimal_number(payload.get("constant_balance"), "constant_balance")
            days = payload.get("days")
            if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
                raise ValueError("days must be a positive integer when using constant_balance")
            balances = [balance] * days
            day_count = days

        # APY is modeled as effective annual yield. Convert it to a daily rate.
        checking_selected = max(checking) if checking else Decimal("0")
        card_selected = max(cards) if cards else Decimal("0")
        relationship_total = sum(relationship, Decimal("0"))
        tier_total = sum(tier, Decimal("0"))
        expected_apy = base + checking_selected + card_selected + relationship_total + tier_total
        daily_rate = (Decimal("1") + expected_apy / Decimal("100")) ** (Decimal("1") / Decimal(days_in_year)) - Decimal("1")
        expected_unrounded = sum((balance * daily_rate for balance in balances), Decimal("0"))
        expected_interest = money(expected_unrounded)
        amount_difference = money(expected_interest - actual_interest)

        actual_apy = None
        if "actual_apy" in payload and payload["actual_apy"] is not None:
            actual_apy = decimal_number(payload["actual_apy"], "actual_apy")

        credit_ready = amount_difference > 0
        report_ready = credit_ready and actual_apy is not None
        return {
            "status": "ok",
            "model": "effective_apy_with_daily_compounding",
            "days_in_year": days_in_year,
            "days": day_count,
            "components": {
                "base_apy": as_json_number(base),
                "selected_checking_boost": as_json_number(checking_selected),
                "selected_credit_card_bonus": as_json_number(card_selected),
                "relationship_bonus_total": as_json_number(relationship_total),
                "tier_bonus_total": as_json_number(tier_total),
            },
            "expected_apy": as_json_number(expected_apy),
            "actual_apy": as_json_number(actual_apy) if actual_apy is not None else None,
            "expected_interest": as_json_number(expected_interest),
            "actual_interest": as_json_number(actual_interest),
            "amount_difference": as_json_number(amount_difference),
            "credit_ready": credit_ready,
            "report_ready": report_ready,
            "notes": [
                "Checking and credit-card candidate lists each use only their highest value.",
                "Confirm the product's day-count and rounding rules before operational use.",
                "actual_apy is required for a backend report and must be the actual applied/displayed APY, not an inferred rate.",
            ],
        }
    except ValueError as exc:
        return fail(str(exc))
    except (ArithmeticError, OverflowError) as exc:
        return fail(f"calculation failed: {exc}")


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
    except Exception as exc:
        json.dump(fail(f"invalid JSON input: {exc}"), sys.stdout)
        sys.stdout.write("\n")
        sys.exit(0)
    json.dump(main(incoming), sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
