#!/usr/bin/env python3
"""Estimate daily-compounded interest from JSON input; reads stdin and writes JSON."""
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP


def number(value, field, errors):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"{field} must be a number")
        return None
    if not math.isfinite(float(value)):
        errors.append(f"{field} must be finite")
        return None
    return float(value)


def money(value):
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def project(account, index):
    errors = []
    label = account.get("name", f"account_{index + 1}")
    if not isinstance(label, str) or not label:
        errors.append("name must be a nonempty string when supplied")
        label = f"account_{index + 1}"

    parts = []
    for key in ("base_apy_pct", "checking_boost_pct", "card_boost_pct"):
        value = number(account.get(key, 0), key, errors)
        if value is not None:
            if value < 0:
                errors.append(f"{key} cannot be negative")
            parts.append(value)
    total_apy = sum(parts) if len(parts) == 3 else None
    if total_apy is not None and total_apy <= -100:
        errors.append("combined APY must be greater than -100%")

    balances = account.get("daily_balances")
    if balances is not None:
        if not isinstance(balances, list) or not balances:
            errors.append("daily_balances must be a nonempty array")
            balances = []
        parsed = []
        for day, balance in enumerate(balances, 1):
            value = number(balance, f"daily_balances[{day - 1}]", errors)
            if value is not None:
                if value < 0:
                    errors.append(f"daily_balances[{day - 1}] cannot be negative")
                parsed.append(value)
        if "balance" in account or "days" in account:
            errors.append("use daily_balances alone, or use balance with days")
        balances = parsed
    else:
        balance = number(account.get("balance"), "balance", errors)
        if balance is not None and balance < 0:
            errors.append("balance cannot be negative")
        days = account.get("days")
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            errors.append("days must be a positive integer")
        balances = [balance] * days if balance is not None and isinstance(days, int) and days > 0 else []

    if errors:
        return {"name": label, "errors": errors}

    daily_rate = (1.0 + total_apy / 100.0) ** (1.0 / 365.0) - 1.0
    accrued = 0.0
    for principal in balances:
        accrued += (principal + accrued) * daily_rate
    return {
        "name": label,
        "accrual_days": len(balances),
        "base_apy_pct": account.get("base_apy_pct", 0),
        "checking_boost_pct": account.get("checking_boost_pct", 0),
        "card_boost_pct": account.get("card_boost_pct", 0),
        "total_apy_pct": total_apy,
        "daily_rate": daily_rate,
        "estimated_interest_unrounded": accrued,
        "estimated_interest_display": money(accrued),
        "assumption": "APY is treated as an effective annual yield; supplied daily balances exclude accrued interest."
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON: {exc}"]}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts"), list) or not payload["accounts"]:
        print(json.dumps({"ok": False, "errors": ["accounts must be a nonempty array"]}))
        return
    results = []
    all_errors = []
    for i, account in enumerate(payload["accounts"]):
        if not isinstance(account, dict):
            results.append({"name": f"account_{i + 1}", "errors": ["account must be an object"]})
            all_errors.append(f"account_{i + 1}: account must be an object")
            continue
        result = project(account, i)
        results.append(result)
        for error in result.get("errors", []):
            all_errors.append(f"{result['name']}: {error}")
    output = {"ok": not all_errors, "accounts": results}
    if all_errors:
        output["errors"] = all_errors
    print(json.dumps(output, separators=(",", ":")))


if __name__ == "__main__":
    main()
