#!/usr/bin/env python3
"""Calculate expected daily-compounded savings interest from JSON stdin.

Input object:
  annual_apy_percent: numeric string/number greater than -100
  daily_principal_balances: non-empty chronological list of numeric strings/numbers
  posted_interest: optional numeric string/number

Output object contains calculation assumptions, daily rate, expected interest, and
comparison values as decimal strings. It exits nonzero with a JSON error object for
invalid input. Balances must already be verified as eligible for the stated APY.
"""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def fail(message):
    print(json.dumps({"ok": False, "error": message}))
    raise SystemExit(2)


def decimal_value(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail(f"{field} must be numeric")
    if not number.is_finite():
        fail(f"{field} must be finite")
    return number


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        fail("stdin must be one JSON object")
    if not isinstance(data, dict):
        fail("stdin must be one JSON object")

    apy_percent = decimal_value(data.get("annual_apy_percent"), "annual_apy_percent")
    if apy_percent <= Decimal("-100"):
        fail("annual_apy_percent must be greater than -100")
    balances = data.get("daily_principal_balances")
    if not isinstance(balances, list) or not balances:
        fail("daily_principal_balances must be a non-empty list")
    principals = []
    for index, value in enumerate(balances):
        principal = decimal_value(value, f"daily_principal_balances[{index}]")
        if principal < 0:
            fail("daily_principal_balances cannot contain a negative balance")
        principals.append(principal)

    # An APY is an effective annual yield. This equivalent daily rate preserves the
    # annual APY under 365 days of daily compounding.
    apy_fraction = float(apy_percent / Decimal("100"))
    daily_rate = Decimal(str(math.pow(1.0 + apy_fraction, 1.0 / 365.0) - 1.0))

    accrued = Decimal("0")
    for principal in principals:
        accrued += (principal + accrued) * daily_rate

    output = {
        "ok": True,
        "days": len(principals),
        "annual_apy_percent": str(apy_percent),
        "effective_daily_rate": format(daily_rate, ".16g"),
        "assumption": "Each supplied balance is that day's eligible principal; accrued but unposted interest compounds daily and balances already reflect any eligibility filtering.",
        "expected_interest_unrounded": str(accrued),
        "expected_interest_rounded": money(accrued),
    }
    if "posted_interest" in data and data["posted_interest"] is not None:
        posted = decimal_value(data["posted_interest"], "posted_interest")
        difference = accrued - posted
        output["posted_interest"] = money(posted)
        output["difference_expected_minus_posted"] = money(difference)
        output["positive_underpayment"] = money(max(difference, Decimal("0")))
        output["overpayment"] = money(max(-difference, Decimal("0")))
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
