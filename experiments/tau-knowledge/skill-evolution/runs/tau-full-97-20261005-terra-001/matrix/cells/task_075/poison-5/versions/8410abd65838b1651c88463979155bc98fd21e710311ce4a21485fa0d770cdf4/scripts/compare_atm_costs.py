#!/usr/bin/env python3
"""Compute documented foreign-ATM costs from JSON supplied on stdin.

The program deliberately does not estimate missing third-party operator fees.
"""
import json
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def decimal(value, field):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if value < ZERO:
        raise ValueError(f"{field} cannot be negative")
    return value


def as_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def fee_for_withdrawal(amount, policy):
    kind = policy.get("type")
    if kind == "zero":
        return ZERO
    if kind == "flat":
        return decimal(policy.get("amount"), "foreign_atm_fee.amount")
    if kind == "percent_min":
        pct = decimal(policy.get("rate_percent"), "foreign_atm_fee.rate_percent")
        minimum = decimal(policy.get("minimum"), "foreign_atm_fee.minimum")
        return max(amount * pct / Decimal("100"), minimum)
    if kind == "percent_max":
        pct = decimal(policy.get("rate_percent"), "foreign_atm_fee.rate_percent")
        maximum = decimal(policy.get("maximum"), "foreign_atm_fee.maximum")
        return min(amount * pct / Decimal("100"), maximum)
    if kind == "tiered":
        tiers = policy.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("foreign_atm_fee.tiers must be a nonempty list")
        previous = None
        for tier in tiers:
            ceiling = tier.get("up_to")
            ceiling = None if ceiling is None else decimal(ceiling, "tier.up_to")
            if ceiling is not None and previous is not None and ceiling < previous:
                raise ValueError("tier ceilings must be sorted ascending")
            if ceiling is None or amount <= ceiling:
                return decimal(tier.get("fee"), "tier.fee")
            previous = ceiling
        raise ValueError("tiered policy does not cover this withdrawal amount")
    if kind == "free_allowance_then_flat":
        # The caller applies the free-use count, then requests the flat fee.
        return decimal(policy.get("amount"), "foreign_atm_fee.amount")
    raise ValueError("unsupported foreign_atm_fee.type")


def main(payload):
    errors = []
    months = payload.get("months")
    products = payload.get("products")
    if not isinstance(months, list) or not months:
        return {"errors": ["months must be a nonempty list"], "products": []}
    if not isinstance(products, list) or not products:
        return {"errors": ["products must be a nonempty list"], "products": []}

    parsed_months = []
    operator_presence = []
    try:
        for month_index, month in enumerate(months, 1):
            if not isinstance(month, list):
                raise ValueError(f"months[{month_index}] must be a list")
            parsed = []
            for withdrawal_index, withdrawal in enumerate(month, 1):
                if not isinstance(withdrawal, dict) or "amount" not in withdrawal:
                    raise ValueError(f"months[{month_index}][{withdrawal_index}] needs amount")
                amount = decimal(withdrawal["amount"], "withdrawal amount")
                has_operator = "operator_fee" in withdrawal and withdrawal["operator_fee"] is not None
                operator = decimal(withdrawal["operator_fee"], "operator_fee") if has_operator else None
                parsed.append((amount, operator))
                operator_presence.append(has_operator)
            parsed_months.append(parsed)
    except ValueError as exc:
        return {"errors": [str(exc)], "products": []}

    operators_known = all(operator_presence) if operator_presence else False
    if any(operator_presence) and not operators_known:
        errors.append("operator_fee must be present for every withdrawal or omitted for all withdrawals")

    daily_totals = payload.get("daily_totals")
    if daily_totals is not None and (not isinstance(daily_totals, list) or len(daily_totals) != len(months)):
        errors.append("daily_totals, when provided, must have one list per month")

    result_products = []
    for product in products:
        name = product.get("name", "unnamed product")
        item = {"name": name, "errors": [], "warnings": []}
        eligible = bool(product.get("eligible", False)) and bool(product.get("opening_requirements_met", False))
        item["eligible"] = eligible
        if not bool(product.get("eligible", False)):
            item["errors"].append("product eligibility is not confirmed")
        if not bool(product.get("opening_requirements_met", False)):
            item["errors"].append("opening or required-balance requirements are not confirmed")
        try:
            policy = product["foreign_atm_fee"]
            cap = decimal(product.get("operator_rebate_monthly_cap", "0"), "operator_rebate_monthly_cap")
            maintenance = decimal(product.get("monthly_maintenance_fee", "0"), "monthly_maintenance_fee")
            waived = bool(product.get("maintenance_waived", False))
            limit_value = product.get("daily_atm_limit")
            limit = decimal(limit_value, "daily_atm_limit") if limit_value is not None else None

            bank_total = ZERO
            operator_total = ZERO
            rebate_total = ZERO
            limit_warnings = []
            for month_index, month in enumerate(parsed_months, 1):
                free_left = int(policy.get("free_withdrawals", 0)) if policy.get("type") == "free_allowance_then_flat" else 0
                month_bank = ZERO
                month_operator = ZERO
                for withdrawal_index, (amount, op_fee) in enumerate(month, 1):
                    if limit is not None and amount > limit:
                        limit_warnings.append(f"month {month_index}, withdrawal {withdrawal_index} exceeds daily ATM limit")
                    if policy.get("type") == "free_allowance_then_flat" and free_left > 0:
                        fee = ZERO
                        free_left -= 1
                    else:
                        fee = fee_for_withdrawal(amount, policy)
                    month_bank += fee
                    if op_fee is not None:
                        month_operator += op_fee
                bank_total += month_bank
                if operators_known:
                    operator_total += month_operator
                    rebate_total += min(month_operator, cap)

                if daily_totals is None:
                    continue
                month_days = daily_totals[month_index - 1]
                if not isinstance(month_days, list):
                    raise ValueError(f"daily_totals[{month_index}] must be a list")
                if limit is not None:
                    for day_index, daily_total in enumerate(month_days, 1):
                        if decimal(daily_total, "daily total") > limit:
                            limit_warnings.append(f"month {month_index}, day {day_index} total exceeds daily ATM limit")

            maintenance_total = ZERO if waived else maintenance * len(parsed_months)
            item.update({
                "bank_foreign_atm_fees": as_money(bank_total),
                "maintenance_fees": as_money(maintenance_total),
                "maximum_documented_operator_rebate": as_money(cap * len(parsed_months)),
                "daily_limit_warnings": limit_warnings,
            })
            if daily_totals is None and limit is not None:
                item["warnings"].append("daily withdrawal grouping was not supplied; aggregate daily-limit compliance is unconfirmed")
            if operators_known:
                item["operator_fees_before_rebates"] = as_money(operator_total)
                item["operator_fee_rebates"] = as_money(rebate_total)
                item["net_operator_fees"] = as_money(operator_total - rebate_total)
                item["total_atm_cost"] = as_money(bank_total + maintenance_total + operator_total - rebate_total)
                item["total_atm_cost_known"] = True
            else:
                item["operator_fees_before_rebates"] = None
                item["operator_fee_rebates"] = None
                item["net_operator_fees"] = None
                item["total_atm_cost"] = None
                item["total_atm_cost_known"] = False
                item["warnings"].append("third-party operator fees are unknown; an exact total ATM cost cannot be calculated")
        except (KeyError, ValueError, TypeError) as exc:
            item["errors"].append(str(exc))
        result_products.append(item)

    return {
        "errors": errors,
        "operator_fees_known": operators_known,
        "month_count": len(parsed_months),
        "withdrawal_count": sum(len(month) for month in parsed_months),
        "products": result_products,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"errors": [str(exc)], "products": []}, separators=(",", ":")))
