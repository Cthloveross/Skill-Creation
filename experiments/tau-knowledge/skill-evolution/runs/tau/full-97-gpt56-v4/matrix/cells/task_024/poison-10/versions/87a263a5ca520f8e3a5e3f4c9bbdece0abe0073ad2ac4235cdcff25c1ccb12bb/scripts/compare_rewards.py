#!/usr/bin/env python3
"""Calculate transparent purchase-return comparisons from explicitly supplied rates.

Reads JSON from stdin. See SKILL.md for the input/output schema.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def number(value, field, option_name):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{option_name}: {field} must be numeric")
    if result < 0:
        raise ValueError(f"{option_name}: {field} cannot be negative")
    return result


def calculate(amount, option):
    name = option.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Each option needs a nonempty name")

    base_rate = number(option.get("base_rate_percent"), "base_rate_percent", name)
    use_conditional = bool(option.get("conditional_rate_applies", False))
    rate = base_rate
    rate_basis = "base"
    if use_conditional:
        if "conditional_rate_percent" not in option:
            raise ValueError(f"{name}: conditional_rate_percent is required when selected")
        rate = number(option["conditional_rate_percent"], "conditional_rate_percent", name)
        rate_basis = "conditional"

    multiplier = number(option.get("promotion_multiplier", 1), "promotion_multiplier", name)
    if not bool(option.get("promotion_applies", False)):
        multiplier = Decimal("1")

    effective_rate = rate * multiplier
    purchase_reward = money(amount * effective_rate / Decimal("100"))
    fee = money(number(option.get("first_year_fee", option.get("annual_fee", 0)), "first_year_fee", name))

    welcome_credit = number(option.get("welcome_credit", 0), "welcome_credit", name)
    welcome_possible = bool(option.get("welcome_requirement_may_be_met", False))
    counted_welcome = money(welcome_credit) if welcome_possible else Decimal("0.00")
    total = money(purchase_reward + counted_welcome - fee)

    return {
        "name": name,
        "rate_basis": rate_basis,
        "selected_rate_percent": str(rate),
        "promotion_multiplier_used": str(multiplier),
        "effective_rate_percent": str(effective_rate),
        "purchase_reward": str(purchase_reward),
        "first_year_fee": str(fee),
        "welcome_credit_included": str(counted_welcome),
        "welcome_credit_is_conditional": bool(welcome_credit) and welcome_possible,
        "welcome_spend_requirement": (
            str(money(number(option["welcome_spend_requirement"], "welcome_spend_requirement", name)))
            if "welcome_spend_requirement" in option else None
        ),
        "first_year_net_value": str(total),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        amount = number(payload.get("purchase_amount"), "purchase_amount", "input")
        if amount <= 0:
            raise ValueError("purchase_amount must be greater than zero")
        options = payload.get("options")
        if not isinstance(options, list) or not options:
            raise ValueError("options must be a nonempty array")
        results = [calculate(amount, option) for option in options if isinstance(option, dict)]
        if len(results) != len(options):
            raise ValueError("Each option must be a JSON object")
        print(json.dumps({"purchase_amount": str(money(amount)), "comparisons": results}, indent=2))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
