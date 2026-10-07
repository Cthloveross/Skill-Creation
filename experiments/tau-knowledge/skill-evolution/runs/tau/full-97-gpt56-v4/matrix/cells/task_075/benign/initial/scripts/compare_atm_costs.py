#!/usr/bin/env python3
"""Compute repeatable bank-fee comparisons for foreign ATM withdrawal plans.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for schema. This program deliberately models only the supplied bank fee fields.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value, field):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be a nonnegative finite amount")
    return amount


def whole(value, field):
    # Reject bool because bool is a Python int but not a meaningful count.
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative whole number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a nonnegative whole number")
    if str(value).strip() not in (str(number), "+" + str(number)) if isinstance(value, str) else False:
        raise ValueError(f"{field} must be a nonnegative whole number")
    if number < 0:
        raise ValueError(f"{field} must be a nonnegative whole number")
    return number


def format_money(amount):
    return str(amount.quantize(CENT, rounding=ROUND_HALF_UP))


def calculate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    months = whole(payload.get("months"), "months")
    withdrawals = whole(payload.get("withdrawals_per_month"), "withdrawals_per_month")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty list")

    results = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            raise ValueError(f"accounts[{index}] must be an object")
        name = account.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"accounts[{index}].name must be a nonempty string")
        waived = account.get("maintenance_fee_waived")
        if not isinstance(waived, bool):
            raise ValueError(f"accounts[{index}].maintenance_fee_waived must be boolean")
        maintenance = money(account.get("monthly_maintenance_fee"), "monthly_maintenance_fee")
        free = whole(account.get("free_foreign_withdrawals_per_month"), "free_foreign_withdrawals_per_month")
        atm_rate = money(account.get("foreign_withdrawal_fee_after_free"), "foreign_withdrawal_fee_after_free")
        charged = max(0, withdrawals - free)
        maintenance_total = Decimal(0) if waived else maintenance * months
        atm_total = atm_rate * charged * months
        total = maintenance_total + atm_total
        results.append({
            "name": name,
            "charged_withdrawals_per_month": charged,
            "maintenance_fees": format_money(maintenance_total),
            "bank_atm_fees": format_money(atm_total),
            "deterministic_total": format_money(total),
        })

    lowest = min(Decimal(item["deterministic_total"]) for item in results)
    return {
        "results": results,
        "lowest_deterministic_total": [
            item["name"] for item in results
            if Decimal(item["deterministic_total"]) == lowest
        ],
        "exclusions": [
            "third-party ATM operator surcharges",
            "operator-fee rebates",
            "currency conversion costs",
            "fees not supplied in the input"
        ]
    }


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(calculate(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
