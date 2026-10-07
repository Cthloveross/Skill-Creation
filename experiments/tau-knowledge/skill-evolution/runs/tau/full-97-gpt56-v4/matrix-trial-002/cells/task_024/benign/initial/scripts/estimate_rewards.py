#!/usr/bin/env python3
"""Compute a transparent net reward estimate from JSON provided on stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def decimal_field(data, name, default=None):
    if name not in data:
        if default is None:
            raise ValueError("missing required field: " + name)
        return Decimal(default)
    value = data[name]
    if isinstance(value, bool) or value is None:
        raise ValueError("invalid decimal field: " + name)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid decimal field: " + name)
    if not result.is_finite():
        raise ValueError("invalid decimal field: " + name)
    return result


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        purchase = decimal_field(data, "purchase_amount")
        base_rate = decimal_field(data, "base_rate_percent")
        multiplier = decimal_field(data, "multiplier", "1")
        fixed_bonus = decimal_field(data, "fixed_bonus", "0")
        annual_fee = decimal_field(data, "annual_fee", "0")
        waived_fee = decimal_field(data, "waived_annual_fee", "0")
        credit = decimal_field(data, "return_or_credit_amount", "0")
        if purchase < 0 or base_rate < 0 or fixed_bonus < 0 or annual_fee < 0 or waived_fee < 0 or credit < 0:
            raise ValueError("amounts and rate must be non-negative")
        if multiplier <= 0:
            raise ValueError("multiplier must be greater than zero")
        if credit > purchase:
            raise ValueError("return_or_credit_amount cannot exceed purchase_amount")
        if waived_fee > annual_fee:
            raise ValueError("waived_annual_fee cannot exceed annual_fee")

        net_purchase = purchase - credit
        effective_rate = base_rate * multiplier
        cash_back = net_purchase * effective_rate / Decimal("100")
        out_of_pocket_fee = annual_fee - waived_fee
        total_rewards = cash_back + fixed_bonus
        net_value = total_rewards - out_of_pocket_fee
        output = {
            "net_purchase": money(net_purchase),
            "effective_rate_percent": str(effective_rate.normalize()),
            "cash_back": money(cash_back),
            "fixed_bonus": money(fixed_bonus),
            "total_rewards": money(total_rewards),
            "out_of_pocket_annual_fee": money(out_of_pocket_fee),
            "net_value_after_fee": money(net_value),
        }
        json.dump(output, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
