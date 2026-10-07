#!/usr/bin/env python3
"""Calculate daily-compounded Silver savings interest from JSON stdin.

The program emits JSON only. It is intentionally calculation-only and never performs
banking actions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
THRESHOLD = Decimal("10000")
LOWER_APY = Decimal("2.5")
HIGHER_APY = Decimal("4.0")
CENT = Decimal("0.01")


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def decimal_text(value):
    return format(value, "f")


def daily_rate_from_apy(apy_percent, days_in_year):
    annual_factor = Decimal(1) + apy_percent / Decimal(100)
    if annual_factor <= 0:
        raise ValueError("combined APY must be greater than -100%")
    # Decimal fractional powers are not consistently available across supported
    # Python versions. The float conversion is restricted to this rate derivation;
    # balances and accruals remain Decimal values.
    rate = Decimal(str(float(annual_factor) ** (1.0 / days_in_year) - 1.0))
    if not rate.is_finite():
        raise ValueError("unable to derive daily rate")
    return rate


def calculate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balances = payload.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        raise ValueError("daily_balances must be a nonempty array")

    days_raw = payload.get("days_in_year", 365)
    if isinstance(days_raw, bool):
        raise ValueError("days_in_year must be a positive integer")
    try:
        days_in_year = int(days_raw)
    except (TypeError, ValueError):
        raise ValueError("days_in_year must be a positive integer")
    if days_in_year <= 0 or str(days_raw) not in (str(days_in_year), f"{days_in_year}.0"):
        raise ValueError("days_in_year must be a positive integer")

    checking = decimal_value(payload.get("checking_bonus_percent", 0), "checking_bonus_percent")
    relationship = decimal_value(payload.get("relationship_bonus_percent", 0), "relationship_bonus_percent")
    card = decimal_value(payload.get("card_bonus_percent", 0), "card_bonus_percent")
    fixed_bonus = checking + relationship + card

    accrued = Decimal(0)
    audit_rows = []
    for index, entry in enumerate(balances, start=1):
        if isinstance(entry, dict):
            if "balance" not in entry:
                raise ValueError(f"daily_balances[{index - 1}].balance is required")
            balance = decimal_value(entry["balance"], f"daily_balances[{index - 1}].balance")
            base = (decimal_value(entry["base_apy_percent"], f"daily_balances[{index - 1}].base_apy_percent")
                    if "base_apy_percent" in entry
                    else (HIGHER_APY if balance >= THRESHOLD else LOWER_APY))
        else:
            balance = decimal_value(entry, f"daily_balances[{index - 1}]")
            base = HIGHER_APY if balance >= THRESHOLD else LOWER_APY
        if balance < 0:
            raise ValueError(f"daily_balances[{index - 1}] must not be negative")

        apy = base + fixed_bonus
        rate = daily_rate_from_apy(apy, days_in_year)
        opening_with_accrual = balance + accrued
        day_interest = opening_with_accrual * rate
        accrued += day_interest
        audit_rows.append({
            "day": index,
            "ending_balance": decimal_text(balance),
            "base_apy_percent": decimal_text(base),
            "combined_apy_percent": decimal_text(apy),
            "daily_periodic_rate": decimal_text(rate),
            "daily_interest": decimal_text(day_interest),
        })

    return {
        "ok": True,
        "days": len(audit_rows),
        "components_percent": {
            "checking": decimal_text(checking),
            "relationship": decimal_text(relationship),
            "card": decimal_text(card),
        },
        "daily_accruals": audit_rows,
        "unrounded_interest": decimal_text(accrued),
        "interest_rounded_to_currency": decimal_text(accrued.quantize(CENT, rounding=ROUND_HALF_UP)),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        output = calculate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {"ok": False, "error": str(exc)}
    except Exception:
        output = {"ok": False, "error": "unexpected calculation failure"}
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
