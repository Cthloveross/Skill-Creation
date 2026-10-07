#!/usr/bin/env python3
"""Calculate an ATM daily-limit and available-balance assessment.

Input JSON object:
  requested_amount (required): nonnegative decimal string/number
  daily_atm_limit (optional): nonnegative decimal string/number
  daily_atm_used (optional): nonnegative decimal string/number
  available_balance (optional): nonnegative decimal string/number
Output JSON object has normalized dollar strings, known flags, and a conservative
assessment. The script performs no banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value, field, required=False):
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal amount")
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a nonnegative decimal amount")
    return amount


def fmt(value):
    return format(value.quantize(CENT), ".2f")


def main(data):
    requested = money(data.get("requested_amount"), "requested_amount", True)
    limit = money(data.get("daily_atm_limit"), "daily_atm_limit")
    used = money(data.get("daily_atm_used"), "daily_atm_used")
    available = money(data.get("available_balance"), "available_balance")

    out = {
        "requested_amount": fmt(requested),
        "limit_known": limit is not None,
        "usage_known": used is not None,
        "available_balance_known": available is not None,
        "remaining_atm_capacity": None,
        "within_daily_atm_limit": "unknown",
        "within_available_balance": "unknown",
        "authorization_assessment": "unknown",
        "notes": [],
    }
    if limit is None or used is None:
        out["notes"].append("Daily ATM limit or usage is missing; remaining daily capacity cannot be established.")
    else:
        remaining = max(Decimal("0.00"), limit - used)
        out["daily_atm_limit"] = fmt(limit)
        out["daily_atm_used"] = fmt(used)
        out["remaining_atm_capacity"] = fmt(remaining)
        out["within_daily_atm_limit"] = requested <= remaining
        if used > limit:
            out["notes"].append("Reported daily usage exceeds the reported limit; verify live card data.")
    if available is None:
        out["notes"].append("Available balance is missing; posted balance and authorization holds must be reviewed.")
    else:
        out["available_balance"] = fmt(available)
        out["within_available_balance"] = requested <= available

    limit_ok = out["within_daily_atm_limit"]
    funds_ok = out["within_available_balance"]
    if limit_ok is False or funds_ok is False:
        out["authorization_assessment"] = "not_supported_by_known_limit_or_balance"
    elif limit_ok is True and funds_ok is True:
        out["authorization_assessment"] = "supported_by_known_limit_and_available_balance_only"
        out["notes"].append("Card status, account status, fraud/security blocks, PIN state, geography, and ATM operator limits still require separate checks.")
    return out


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
