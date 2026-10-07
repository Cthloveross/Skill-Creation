#!/usr/bin/env python3
"""Compute documented foreign-ATM comparison figures from JSON stdin.

Optional product terms are represented as not established; they are never
silently converted to zero. The program performs no external or banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def number(value, label):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a decimal number")
    if not result.is_finite() or result < ZERO:
        raise ValueError(f"{label} must be a nonnegative finite decimal")
    return result


def optional_number(data, key, label):
    if key not in data or data[key] is None:
        return None
    return number(data[key], label)


def as_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_months(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError("months must be a nonempty list")
    months = []
    has_operator_fee = []
    for month_i, month in enumerate(raw, 1):
        if not isinstance(month, list):
            raise ValueError(f"months[{month_i}] must be a list")
        parsed_month = []
        for withdrawal_i, withdrawal in enumerate(month, 1):
            if not isinstance(withdrawal, dict) or "amount" not in withdrawal:
                raise ValueError(f"months[{month_i}][{withdrawal_i}] requires amount")
            amount = number(withdrawal["amount"], "withdrawal amount")
            present = "operator_fee" in withdrawal and withdrawal["operator_fee"] is not None
            fee = number(withdrawal["operator_fee"], "operator_fee") if present else None
            parsed_month.append((amount, fee))
            has_operator_fee.append(present)
        months.append(parsed_month)
    if any(has_operator_fee) and not all(has_operator_fee):
        raise ValueError("operator_fee must be present for every withdrawal or omitted for all")
    return months, bool(has_operator_fee) and all(has_operator_fee)


def fee_for_withdrawal(amount, policy):
    if not isinstance(policy, dict):
        raise ValueError("foreign_atm_fee must be an object")
    kind = policy.get("type")
    if kind == "zero":
        return ZERO
    if kind == "flat" or kind == "free_allowance_then_flat":
        return number(policy.get("amount"), "foreign_atm_fee.amount")
    rate = number(policy.get("rate_percent"), "foreign_atm_fee.rate_percent")
    if kind == "percent_min":
        return max(amount * rate / 100, number(policy.get("minimum"), "foreign_atm_fee.minimum"))
    if kind == "percent_max":
        return min(amount * rate / 100, number(policy.get("maximum"), "foreign_atm_fee.maximum"))
    raise ValueError("unsupported foreign_atm_fee.type")


def calculate_product(product, months, operator_known):
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
        maintenance = optional_number(product, "monthly_maintenance_fee", "monthly_maintenance_fee")
        rebate_cap = optional_number(product, "operator_rebate_monthly_cap", "operator_rebate_monthly_cap")
        markup = optional_number(product, "currency_conversion_markup_percent", "currency_conversion_markup_percent")
        daily_limit = optional_number(product, "daily_atm_limit", "daily_atm_limit")
        waived = bool(product.get("maintenance_waived", False))

        total_amount = ZERO
        bank_fees = ZERO
        known_operator_fees = ZERO
        rebates = ZERO
        limit_warnings = []
        for month_i, month in enumerate(months, 1):
            free_remaining = 0
            if policy.get("type") == "free_allowance_then_flat":
                free_remaining = policy.get("free_withdrawals")
                if not isinstance(free_remaining, int) or free_remaining < 0:
                    raise ValueError("foreign_atm_fee.free_withdrawals must be a nonnegative integer")
            month_operator_fees = ZERO
            for withdrawal_i, (amount, operator_fee) in enumerate(month, 1):
                total_amount += amount
                if daily_limit is not None and amount > daily_limit:
                    limit_warnings.append(f"month {month_i}, withdrawal {withdrawal_i} exceeds daily ATM limit")
                if free_remaining:
                    free_remaining -= 1
                else:
                    bank_fees += fee_for_withdrawal(amount, policy)
                if operator_fee is not None:
                    month_operator_fees += operator_fee
            if operator_known:
                known_operator_fees += month_operator_fees
                if rebate_cap is not None:
                    rebates += min(month_operator_fees, rebate_cap)

        maintenance_total = None if maintenance is None else (ZERO if waived else maintenance * len(months))
        conversion_total = None if markup is None else total_amount * markup / 100
        established_subtotal = bank_fees
        exact_total_possible = operator_known
        if maintenance_total is None:
            exact_total_possible = False
        else:
            established_subtotal += maintenance_total
        if conversion_total is None:
            exact_total_possible = False
        else:
            established_subtotal += conversion_total

        result.update({
            "withdrawal_amount_total": as_money(total_amount),
            "bank_foreign_atm_fees": as_money(bank_fees),
            "maintenance_fees": None if maintenance_total is None else as_money(maintenance_total),
            "maintenance_fee_established": maintenance is not None,
            "currency_conversion_markup_percent": None if markup is None else str(markup),
            "currency_conversion_markup_cost": None if conversion_total is None else as_money(conversion_total),
            "conversion_markup_established": markup is not None,
            "maximum_documented_operator_rebate": None if rebate_cap is None else as_money(rebate_cap * len(months)),
            "operator_rebate_established": rebate_cap is not None,
            "daily_limit_warnings": limit_warnings,
            "daily_limit_established": daily_limit is not None,
            "documented_cost_subtotal": as_money(established_subtotal),
        })
        if daily_limit is not None:
            result["warnings"].append("only individual withdrawals were checked; combined same-day withdrawals must remain within the daily limit")
        if maintenance is None:
            result["warnings"].append("monthly maintenance fee is not established and is excluded from documented_cost_subtotal")
        if markup is None:
            result["warnings"].append("conversion markup is not established and is excluded from documented_cost_subtotal")
        if operator_known and rebate_cap is not None:
            net_operator = known_operator_fees - rebates
            result.update({
                "operator_fees_before_rebates": as_money(known_operator_fees),
                "operator_fee_rebates": as_money(rebates),
                "net_operator_fees": as_money(net_operator),
            })
            established_subtotal += net_operator
        else:
            result.update({
                "operator_fees_before_rebates": None,
                "operator_fee_rebates": None,
                "net_operator_fees": None,
            })
            exact_total_possible = False
            result["warnings"].append("operator charges or their rebate treatment are unknown; no final total is calculated")
        result["total_cost_known"] = exact_total_possible
        result["total_known_cost"] = as_money(established_subtotal) if exact_total_possible else None
        if not result["eligible"]:
            result["warnings"].append("product eligibility is not confirmed")
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        result["errors"].append(str(error))
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    months, operator_known = parse_months(payload.get("months"))
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty list")
    return {
        "errors": [],
        "month_count": len(months),
        "withdrawal_count": sum(len(month) for month in months),
        "operator_fees_known": operator_known,
        "products": [calculate_product(product, months, operator_known) for product in products],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"errors": [str(error)], "products": []}, separators=(",", ":")))
