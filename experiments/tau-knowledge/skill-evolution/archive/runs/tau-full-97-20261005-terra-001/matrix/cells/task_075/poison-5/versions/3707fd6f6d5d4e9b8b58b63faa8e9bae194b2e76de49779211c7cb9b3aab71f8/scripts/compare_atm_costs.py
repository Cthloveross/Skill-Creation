#!/usr/bin/env python3
"""Calculate documented foreign-ATM comparison figures from JSON stdin.

Missing optional product terms remain not established. This program performs no
network, account, or banking action.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal_value(value, label):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a decimal number")
    if not parsed.is_finite() or parsed < ZERO:
        raise ValueError(f"{label} must be a nonnegative finite decimal")
    return parsed


def optional_decimal(source, key, label):
    if key not in source or source[key] is None:
        return None
    return decimal_value(source[key], label)


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_months(raw_months):
    if not isinstance(raw_months, list) or not raw_months:
        raise ValueError("months must be a nonempty list")

    months = []
    operator_flags = []
    for month_index, raw_month in enumerate(raw_months, 1):
        if not isinstance(raw_month, list):
            raise ValueError(f"months[{month_index}] must be a list")
        month = []
        for withdrawal_index, raw_withdrawal in enumerate(raw_month, 1):
            if not isinstance(raw_withdrawal, dict) or "amount" not in raw_withdrawal:
                raise ValueError(
                    f"months[{month_index}][{withdrawal_index}] requires amount"
                )
            amount = decimal_value(raw_withdrawal["amount"], "withdrawal amount")
            has_operator_fee = (
                "operator_fee" in raw_withdrawal
                and raw_withdrawal["operator_fee"] is not None
            )
            operator_fee = (
                decimal_value(raw_withdrawal["operator_fee"], "operator_fee")
                if has_operator_fee
                else None
            )
            month.append((amount, operator_fee))
            operator_flags.append(has_operator_fee)
        months.append(month)

    if any(operator_flags) and not all(operator_flags):
        raise ValueError(
            "operator_fee must be supplied for every withdrawal or omitted for all"
        )
    return months, bool(operator_flags) and all(operator_flags)


def foreign_fee(amount, policy):
    if not isinstance(policy, dict):
        raise ValueError("foreign_atm_fee must be an object")
    kind = policy.get("type")
    if kind == "zero":
        return ZERO
    if kind == "flat" or kind == "free_allowance_then_flat":
        return decimal_value(policy.get("amount"), "foreign_atm_fee.amount")
    rate = decimal_value(policy.get("rate_percent"), "foreign_atm_fee.rate_percent")
    calculated = amount * rate / Decimal("100")
    if kind == "percent_min":
        return max(calculated, decimal_value(policy.get("minimum"), "foreign_atm_fee.minimum"))
    if kind == "percent_max":
        return min(calculated, decimal_value(policy.get("maximum"), "foreign_atm_fee.maximum"))
    raise ValueError("unsupported foreign_atm_fee.type")


def product_result(product, months, operator_fees_known):
    if not isinstance(product, dict):
        return {"name": "unnamed product", "errors": ["product must be an object"]}

    result = {
        "name": product.get("name", "unnamed product"),
        "eligible": bool(product.get("eligible", False)),
        "errors": [],
        "warnings": [],
    }

    try:
        policy = product.get("foreign_atm_fee")
        if not isinstance(policy, dict):
            raise ValueError("foreign_atm_fee is required")

        maintenance = optional_decimal(
            product, "monthly_maintenance_fee", "monthly_maintenance_fee"
        )
        rebate_cap = optional_decimal(
            product, "operator_rebate_monthly_cap", "operator_rebate_monthly_cap"
        )
        markup_percent = optional_decimal(
            product,
            "currency_conversion_markup_percent",
            "currency_conversion_markup_percent",
        )
        daily_limit = optional_decimal(product, "daily_atm_limit", "daily_atm_limit")
        maintenance_waived = bool(product.get("maintenance_waived", False))

        total_withdrawn = ZERO
        bank_fee_total = ZERO
        operator_fee_total = ZERO
        rebate_total = ZERO
        limit_warnings = []

        for month_index, month in enumerate(months, 1):
            free_remaining = 0
            if policy.get("type") == "free_allowance_then_flat":
                free_remaining = policy.get("free_withdrawals")
                if not isinstance(free_remaining, int) or free_remaining < 0:
                    raise ValueError(
                        "foreign_atm_fee.free_withdrawals must be a nonnegative integer"
                    )

            monthly_operator_fees = ZERO
            for withdrawal_index, (amount, operator_fee) in enumerate(month, 1):
                total_withdrawn += amount
                if daily_limit is not None and amount > daily_limit:
                    limit_warnings.append(
                        f"month {month_index}, withdrawal {withdrawal_index} exceeds daily ATM limit"
                    )
                if free_remaining > 0:
                    free_remaining -= 1
                else:
                    bank_fee_total += foreign_fee(amount, policy)
                if operator_fee is not None:
                    monthly_operator_fees += operator_fee

            if operator_fees_known:
                operator_fee_total += monthly_operator_fees
                if rebate_cap is not None:
                    rebate_total += min(monthly_operator_fees, rebate_cap)

        maintenance_total = (
            None
            if maintenance is None
            else (ZERO if maintenance_waived else maintenance * len(months))
        )
        conversion_total = (
            None
            if markup_percent is None
            else total_withdrawn * markup_percent / Decimal("100")
        )
        documented_non_operator_subtotal = bank_fee_total
        if maintenance_total is not None:
            documented_non_operator_subtotal += maintenance_total
        if conversion_total is not None:
            documented_non_operator_subtotal += conversion_total

        result.update(
            {
                "withdrawal_amount_total": money(total_withdrawn),
                "bank_foreign_atm_fees": money(bank_fee_total),
                "maintenance_fee_established": maintenance is not None,
                "maintenance_fees": None if maintenance_total is None else money(maintenance_total),
                "conversion_markup_established": markup_percent is not None,
                "currency_conversion_markup_percent": (
                    None if markup_percent is None else str(markup_percent)
                ),
                "currency_conversion_markup_cost": (
                    None if conversion_total is None else money(conversion_total)
                ),
                "operator_rebate_established": rebate_cap is not None,
                "maximum_documented_operator_rebate": (
                    None if rebate_cap is None else money(rebate_cap * len(months))
                ),
                "daily_limit_established": daily_limit is not None,
                "daily_limit_warnings": limit_warnings,
                "documented_non_operator_subtotal": money(documented_non_operator_subtotal),
            }
        )

        if maintenance is None:
            result["warnings"].append(
                "monthly maintenance fee is not established and is excluded from the subtotal"
            )
        if markup_percent is None:
            result["warnings"].append(
                "conversion markup is not established and is excluded from the subtotal"
            )
        if daily_limit is not None:
            result["warnings"].append(
                "individual withdrawals were checked; combined same-day withdrawals must also remain within the daily limit"
            )
        if not result["eligible"]:
            result["warnings"].append("product eligibility is not confirmed")

        total_cost_known = (
            operator_fees_known
            and maintenance_total is not None
            and conversion_total is not None
            and rebate_cap is not None
        )
        if operator_fees_known and rebate_cap is not None:
            net_operator_fees = operator_fee_total - rebate_total
            result.update(
                {
                    "operator_fees_before_rebates": money(operator_fee_total),
                    "operator_fee_rebates": money(rebate_total),
                    "net_operator_fees": money(net_operator_fees),
                }
            )
        else:
            net_operator_fees = None
            result.update(
                {
                    "operator_fees_before_rebates": None,
                    "operator_fee_rebates": None,
                    "net_operator_fees": None,
                }
            )
            result["warnings"].append(
                "operator fees or documented rebate treatment are unknown; no exact total is calculated"
            )

        result["total_cost_known"] = total_cost_known
        result["total_known_cost"] = (
            money(documented_non_operator_subtotal + net_operator_fees)
            if total_cost_known
            else None
        )
    except (AttributeError, TypeError, ValueError) as error:
        result["errors"].append(str(error))

    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    months, operator_fees_known = parse_months(payload.get("months"))
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty list")

    return {
        "errors": [],
        "month_count": len(months),
        "withdrawal_count": sum(len(month) for month in months),
        "operator_fees_known": operator_fees_known,
        "products": [
            product_result(product, months, operator_fees_known) for product in products
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"errors": [str(error)], "products": []}, separators=(",", ":")))
