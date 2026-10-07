#!/usr/bin/env python3
"""Calculate documented foreign-ATM costs from a JSON object on stdin.

All money is rounded half-up to cents. Unknown third-party operator fees are
never estimated and are excluded from the returned known-cost subtotal.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def decimal(value, label):
    if value is None:
        raise ValueError(f"{label} is required")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a decimal number")
    if not value.is_finite() or value < ZERO:
        raise ValueError(f"{label} must be a nonnegative finite decimal")
    return value


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_months(raw):
    if not isinstance(raw, list) or not raw:
        raise ValueError("months must be a nonempty list")
    months = []
    operator_presence = []
    for month_index, raw_month in enumerate(raw, 1):
        if not isinstance(raw_month, list):
            raise ValueError(f"months[{month_index}] must be a list")
        month = []
        for withdrawal_index, item in enumerate(raw_month, 1):
            if not isinstance(item, dict) or "amount" not in item:
                raise ValueError(
                    f"months[{month_index}][{withdrawal_index}] requires amount"
                )
            amount = decimal(item["amount"], "withdrawal amount")
            has_operator_fee = "operator_fee" in item and item["operator_fee"] is not None
            operator_fee = decimal(item["operator_fee"], "operator_fee") if has_operator_fee else None
            month.append((amount, operator_fee))
            operator_presence.append(has_operator_fee)
        months.append(month)
    if any(operator_presence) and not all(operator_presence):
        raise ValueError("operator_fee must be supplied for every withdrawal or omitted for all")
    return months, bool(operator_presence) and all(operator_presence)


def withdrawal_fee(amount, policy):
    if not isinstance(policy, dict):
        raise ValueError("foreign_atm_fee must be an object")
    kind = policy.get("type")
    if kind == "zero":
        return ZERO
    if kind == "flat":
        return decimal(policy.get("amount"), "foreign_atm_fee.amount")
    if kind == "percent_min":
        rate = decimal(policy.get("rate_percent"), "foreign_atm_fee.rate_percent")
        minimum = decimal(policy.get("minimum"), "foreign_atm_fee.minimum")
        return max(amount * rate / 100, minimum)
    if kind == "percent_max":
        rate = decimal(policy.get("rate_percent"), "foreign_atm_fee.rate_percent")
        maximum = decimal(policy.get("maximum"), "foreign_atm_fee.maximum")
        return min(amount * rate / 100, maximum)
    if kind == "free_allowance_then_flat":
        return decimal(policy.get("amount"), "foreign_atm_fee.amount")
    raise ValueError("unsupported foreign_atm_fee.type")


def calculate_product(product, months, operator_fees_known):
    if not isinstance(product, dict):
        return {"name": "unnamed product", "errors": ["product must be an object"]}
    name = product.get("name", "unnamed product")
    result = {"name": name, "eligible": bool(product.get("eligible", False)), "errors": [], "warnings": []}
    if not result["eligible"]:
        result["warnings"].append("product eligibility is not confirmed")
    try:
        policy = product.get("foreign_atm_fee")
        maintenance_fee = decimal(product.get("monthly_maintenance_fee", "0"), "monthly_maintenance_fee")
        rebate_cap = decimal(product.get("operator_rebate_monthly_cap", "0"), "operator_rebate_monthly_cap")
        markup = decimal(product.get("currency_conversion_markup_percent", "0"), "currency_conversion_markup_percent")
        waived = bool(product.get("maintenance_waived", False))
        raw_limit = product.get("daily_atm_limit")
        daily_limit = None if raw_limit is None else decimal(raw_limit, "daily_atm_limit")

        bank_fees = ZERO
        total_amount = ZERO
        operator_before_rebates = ZERO
        rebates = ZERO
        limit_warnings = []
        for month_number, withdrawals in enumerate(months, 1):
            free_remaining = 0
            if policy.get("type") == "free_allowance_then_flat":
                free_remaining = policy.get("free_withdrawals")
                if not isinstance(free_remaining, int) or free_remaining < 0:
                    raise ValueError("foreign_atm_fee.free_withdrawals must be a nonnegative integer")
            monthly_operator_fees = ZERO
            for withdrawal_number, (amount, operator_fee) in enumerate(withdrawals, 1):
                total_amount += amount
                if daily_limit is not None and amount > daily_limit:
                    limit_warnings.append(
                        f"month {month_number}, withdrawal {withdrawal_number} exceeds daily ATM limit"
                    )
                if free_remaining > 0:
                    free_remaining -= 1
                else:
                    bank_fees += withdrawal_fee(amount, policy)
                if operator_fee is not None:
                    monthly_operator_fees += operator_fee
            if operator_fees_known:
                operator_before_rebates += monthly_operator_fees
                rebates += min(monthly_operator_fees, rebate_cap)

        maintenance_total = ZERO if waived else maintenance_fee * len(months)
        conversion_total = total_amount * markup / 100
        known_base = bank_fees + maintenance_total + conversion_total
        result.update({
            "withdrawal_amount_total": money(total_amount),
            "bank_foreign_atm_fees": money(bank_fees),
            "maintenance_fees": money(maintenance_total),
            "currency_conversion_markup_percent": str(markup),
            "currency_conversion_markup_cost": money(conversion_total),
            "maximum_documented_operator_rebate": money(rebate_cap * len(months)),
            "daily_limit_warnings": limit_warnings,
        })
        if daily_limit is not None:
            result["warnings"].append(
                "only individual withdrawals were checked; combined same-day withdrawals must stay within the daily limit"
            )
        if operator_fees_known:
            net_operator = operator_before_rebates - rebates
            result.update({
                "operator_fees_before_rebates": money(operator_before_rebates),
                "operator_fee_rebates": money(rebates),
                "net_operator_fees": money(net_operator),
                "total_known_cost": money(known_base + net_operator),
                "total_cost_known": True,
            })
        else:
            result.update({
                "operator_fees_before_rebates": None,
                "operator_fee_rebates": None,
                "net_operator_fees": None,
                "total_known_cost": money(known_base),
                "total_cost_known": False,
            })
            result["warnings"].append(
                "third-party operator fees are unknown; total_known_cost is not a final total"
            )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
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
        "operator_fees_known": operator_fees_known,
        "month_count": len(months),
        "withdrawal_count": sum(len(month) for month in months),
        "products": [
            calculate_product(product, months, operator_fees_known)
            for product in products
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"errors": [str(error)], "products": []}, separators=(",", ":")))
