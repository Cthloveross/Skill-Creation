#!/usr/bin/env python3
"""Calculate conditional daily-compounded savings-interest estimates from JSON stdin."""

import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return str(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


def number(value, field, errors, minimum=None):
    if isinstance(value, bool):
        errors.append(f"{field} must be a number, not a boolean")
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not math.isfinite(result):
        errors.append(f"{field} must be finite")
        return None
    if minimum is not None and result < minimum:
        errors.append(f"{field} must be at least {minimum}")
        return None
    return result


def percent_list(value, field, errors):
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    parsed = []
    for index, item in enumerate(value):
        parsed_item = number(item, f"{field}[{index}]", errors, 0)
        if parsed_item is not None:
            parsed.append(parsed_item)
    return parsed


def daily_rate(annual_percent, method):
    annual = annual_percent / 100.0
    if method == "nominal_365":
        return annual / 365.0
    if method == "apy_effective_365":
        return (1.0 + annual) ** (1.0 / 365.0) - 1.0
    raise ValueError("daily_rate_method must be 'nominal_365' or 'apy_effective_365'")


def parse_balances(account, errors):
    supplied_daily = account.get("daily_eligible_balances")
    if supplied_daily is not None:
        if not isinstance(supplied_daily, list) or not supplied_daily:
            errors.append("daily_eligible_balances must be a nonempty array when supplied")
            return []
        balances = []
        for index, value in enumerate(supplied_daily):
            parsed = number(value, f"daily_eligible_balances[{index}]", errors, 0)
            if parsed is not None:
                balances.append(parsed)
        supplied_days = account.get("days")
        if supplied_days is not None:
            if isinstance(supplied_days, bool) or not isinstance(supplied_days, int) or supplied_days <= 0:
                errors.append("days must be a positive integer when supplied")
            elif supplied_days != len(balances):
                errors.append("days must equal the length of daily_eligible_balances")
        return balances

    balance = number(account.get("constant_eligible_balance"), "constant_eligible_balance", errors, 0)
    days = account.get("days")
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        errors.append("days must be a positive integer when using constant_eligible_balance")
        return []
    if balance is None:
        return []
    return [balance] * days


def reconcile_account(account, index):
    errors = []
    if not isinstance(account, dict):
        return None, [f"accounts[{index}] must be an object"]

    name = account.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a nonempty string")
        name = f"account_{index + 1}"
    base = number(account.get("base_apy_percent"), "base_apy_percent", errors, 0)
    checking = percent_list(account.get("linked_checking_boosts_percent", []), "linked_checking_boosts_percent", errors)
    cards = percent_list(account.get("card_bonuses_percent", []), "card_bonuses_percent", errors)
    method = account.get("daily_rate_method", "nominal_365")
    if method not in ("nominal_365", "apy_effective_365"):
        errors.append("daily_rate_method must be 'nominal_365' or 'apy_effective_365'")
    balances = parse_balances(account, errors)
    credited = None
    if "credited_interest" in account:
        credited = number(account["credited_interest"], "credited_interest", errors, 0)

    if errors:
        return None, [f"{name}: {message}" for message in errors]

    selected_checking = max(checking) if checking else 0.0
    selected_card = max(cards) if cards else 0.0
    combined = base + selected_checking + selected_card
    rate = daily_rate(combined, method)

    accrued = 0.0
    for balance in balances:
        accrued += (balance + accrued) * rate

    result = {
        "name": name,
        "base_apy_percent": base,
        "selected_checking_boost_percent": selected_checking,
        "selected_card_bonus_percent": selected_card,
        "combined_apy_percent": combined,
        "daily_rate_method": method,
        "daily_rate_decimal": rate,
        "calculation_days": len(balances),
        "estimated_gross_interest": money(accrued),
        "assumption": "Daily balances are eligible principal balances; selected boosts and bonuses were already confirmed applicable.",
    }
    if credited is not None:
        result["credited_interest"] = money(credited)
        result["estimated_minus_credited"] = money(accrued - credited)
    return result, []


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"Invalid JSON input: {exc.msg}"]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["Top-level JSON must be an object"]}))
        return
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        print(json.dumps({"ok": False, "errors": ["accounts must be a nonempty array"]}))
        return

    results = []
    errors = []
    for index, account in enumerate(accounts):
        result, account_errors = reconcile_account(account, index)
        errors.extend(account_errors)
        if result is not None:
            results.append(result)

    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, sort_keys=True))
        return
    print(json.dumps({"ok": True, "accounts": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
