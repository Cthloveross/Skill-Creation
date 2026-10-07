#!/usr/bin/env python3
"""Assess supplied ATM limit/funds arithmetic without making a banking decision.

Reads the schema documented in SKILL.md from stdin and writes JSON to stdout.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
REQUIRED_FIELDS = (
    "requested_amount",
    "daily_atm_limit",
    "atm_used_today",
    "available_balance",
    "estimated_bank_fee",
)


def parse_amount(value, field, index):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"attempts[{index}].{field} must be a decimal string or null")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"attempts[{index}].{field} is not a valid decimal")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"attempts[{index}].{field} must be finite and non-negative")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def assess(attempt, index):
    if not isinstance(attempt, dict):
        raise ValueError(f"attempts[{index}] must be an object")
    result = {"reference": attempt.get("reference", str(index + 1))}
    values = {field: parse_amount(attempt.get(field), field, index) for field in REQUIRED_FIELDS}
    missing = [field for field, value in values.items() if value is None]
    requested = values["requested_amount"]
    limit = values["daily_atm_limit"]
    used = values["atm_used_today"]
    balance = values["available_balance"]
    fee = values["estimated_bank_fee"]

    if limit is not None and used is not None:
        remaining_limit = max(Decimal("0.00"), limit - used)
        result["remaining_atm_limit"] = money(remaining_limit)
        if requested is not None:
            result["within_remaining_atm_limit"] = requested <= remaining_limit
    else:
        remaining_limit = None
        result["remaining_atm_limit"] = None
        result["within_remaining_atm_limit"] = None

    if requested is not None and fee is not None:
        needed = requested + fee
        result["needed_funds_including_estimated_fee"] = money(needed)
        result["within_available_balance"] = None if balance is None else needed <= balance
    else:
        result["needed_funds_including_estimated_fee"] = None
        result["within_available_balance"] = None

    blockers = []
    if result.get("within_remaining_atm_limit") is False:
        blockers.append("requested_amount_exceeds_remaining_atm_limit")
    if result.get("within_available_balance") is False:
        blockers.append("available_balance_below_requested_amount_plus_estimated_fee")
    result["known_arithmetic_blockers"] = blockers
    result["missing_facts"] = missing
    result["authorization"] = "undetermined"
    result["note"] = (
        "This is arithmetic only. Verify card status, account status, restrictions, "
        "fees, ownership, and ATM/operator availability with banking tools."
    )
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("attempts"), list):
            raise ValueError("input must be an object containing an attempts array")
        output = {"assessments": [assess(item, i) for i, item in enumerate(payload["attempts"])]}
        json.dump(output, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    except (json.JSONDecodeError, ValueError) as exc:
        json.dump({"error": str(exc)}, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
