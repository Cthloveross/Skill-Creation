#!/usr/bin/env python3
"""Compute the annual dollar effect of an APY bonus and annual fee from JSON stdin.

Input: {"balance": USD number, "bonus_apy": percentage-points number,
        "annual_fee": USD number}
Output: {"gross_incremental_interest": USD number, "annual_fee": USD number,
         "net_before_tax": USD number, "errors": [string, ...]}
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def amount(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        errors.append(f"{field} must be a number")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{field} must be a nonnegative number")
        return None
    return result


def main(payload):
    if not isinstance(payload, dict):
        return {"gross_incremental_interest": None, "annual_fee": None, "net_before_tax": None, "errors": ["input must be an object"]}
    errors = []
    balance = amount(payload.get("balance"), "balance", errors)
    bonus = amount(payload.get("bonus_apy"), "bonus_apy", errors)
    fee = amount(payload.get("annual_fee"), "annual_fee", errors)
    if errors:
        return {"gross_incremental_interest": None, "annual_fee": None, "net_before_tax": None, "errors": errors}
    gross = (balance * bonus / Decimal("100")).quantize(CENT, rounding=ROUND_HALF_UP)
    annual_fee = fee.quantize(CENT, rounding=ROUND_HALF_UP)
    net = (gross - annual_fee).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "gross_incremental_interest": float(gross),
        "annual_fee": float(annual_fee),
        "net_before_tax": float(net),
        "errors": [],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"gross_incremental_interest": None, "annual_fee": None, "net_before_tax": None, "errors": [f"invalid JSON: {exc.msg}"]}))
    except Exception as exc:
        print(json.dumps({"gross_incremental_interest": None, "annual_fee": None, "net_before_tax": None, "errors": [f"unexpected error: {type(exc).__name__}"]}))
