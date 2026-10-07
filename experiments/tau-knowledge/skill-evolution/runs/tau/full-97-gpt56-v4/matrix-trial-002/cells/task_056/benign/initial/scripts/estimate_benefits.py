#!/usr/bin/env python3
"""Estimate rewards and capped ATM rebates from runtime-supplied numeric terms.

Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def nonnegative_decimal(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return number


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        spend = nonnegative_decimal(payload.get("monthly_eligible_debit_spend", 0), "monthly_eligible_debit_spend")
        rate = nonnegative_decimal(payload.get("cashback_rate_percent", 0), "cashback_rate_percent")
        fees = nonnegative_decimal(payload.get("monthly_atm_fees", 0), "monthly_atm_fees")
        cap = nonnegative_decimal(payload.get("monthly_atm_rebate_cap", 0), "monthly_atm_rebate_cap")
        cashback = money(spend * rate / Decimal("100"))
        rebate = money(min(fees, cap))
        unreimbursed = money(fees - rebate)
        print(json.dumps({
            "estimated_cashback": float(cashback),
            "estimated_atm_rebate": float(rebate),
            "estimated_unreimbursed_atm_fees": float(unreimbursed),
            "assumptions": [
                "Debit spend is eligible, settles, and has no returns or adjustments.",
                "ATM fees supplied are qualifying fees subject to the supplied monthly rebate cap."
            ]
        }, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
