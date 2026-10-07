#!/usr/bin/env python3
"""Compute documented foreign-ATM costs from JSON on stdin.

Unknown third-party operator fees are deliberately never estimated. All monetary
results are rounded to cents using conventional half-up rounding.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def dec(value, field):
    if value is None:
        raise ValueError(f"{field} is required")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not number.is_finite() or number < ZERO:
        raise ValueError(f"{field} cannot be negative")
    return number


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def fee_for_withdrawal(amount, policy):
    kind = policy.get("type")
    if kind == "zero":
        return ZERO
    if kind == "flat":
        return dec(policy.get("amount"), "foreign_atm_fee.amount")
    if kind == "percent_min":
        return max(
            amount * dec(policy.get("rate_percent"), "foreign_atm_fee.rate_percent") / 100,
            dec(policy.get("minimum"), "foreign_atm_fee.minimum"),
        )
    if kind == "percent_max":
        return min(
            amount * dec(policy.get("rate_percent"), "foreign_atm_fee.rate_percent") / 100,
            dec(policy.get("maximum"), "foreign_atm_fee.maximum"),
        )
    if kind == "tiered":
        tiers = policy.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("foreign_atm_fee.tiers must be a nonempty list")
        prior = None
        for index, tier in enumerate(tiers, 1):
            if not isinstance(tier, dict):
                raise ValueError(f"tier {index} must be an object")
            ceiling_raw = tier.get("up_to")
            ceiling = None if ceiling_raw is None else dec(ceiling_raw, "tier.up_to")
            if ceiling is not None and prior is not None and ceiling < prior:
                raise ValueError("tier ceilings must be sorted ascending")
            if ceiling is None or amount <= ceiling:
                return dec(tier.get("fee"), "tier.fee")
            prior = ceiling
        raise ValueError("tiered policy does not cover this withdrawal amount")
    if kind == "free_allowance_then_flat":
        return dec(policy.get("amount"), "foreign_atm_fee.amount")
    raise ValueError("unsupported foreign_atm_fee.type")


def parse_months(months):
    if not isinstance(months, list) or not months:
        raise ValueError("months must be a nonempty list")
    parsed, operator_flags = [], []
    for month_no, month in enumerate(months, 1):
        if not isinstance(month, list):
            raise ValueError(f"months[{month_no}] must be a list")
        entries = []
        for withdrawal_no, withdrawal in enumerate(month, 1):
            if not isinstance(withdrawal, dict) or "amount" not in withdrawal:
                raise ValueError(f"months[{month_no}][{withdrawal_no}] needs amount")
            amount = dec(withdrawal["amount"], "withdrawal amount")
            known = withdrawal.get("operator_fee") is not None and "operator_fee" in withdrawal
            operator_fee = dec(withdrawal["operator_fee"], "operator_fee") if known else None
            entries.append((amount, operator_fee))
            operator_flags.append(known)
        parsed.append(entries)
    if any(operator_flags) and not all(operator_flags):
        raise ValueError("operator_fee must be present for every withdrawal or omitted for all withdrawals")
    return parsed, bool(operator_flags) and all(operator_flags)


def parse_daily_totals(raw, month_count):
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) != month_count:
        raise ValueError("daily_totals must have one list per month")
    parsed = []
    for month_no, days in enumerate(raw, 1):
        if not isinstance(days, list):
            raise ValueError(f"daily_totals[{month_no}] must be a list")
        parsed.append([dec(day, "daily total") for day in days])
    return parsed


def product_result(product, months, operators_known, daily_totals):
    if not isinstance(product, dict):
        return {"name": "unnamed product", "errors": ["product must be an object"], "warnings": []}
    name = product.get("name", "unnamed product")
    item = {"name": name, "errors": [], "warnings": []}
    eligibility_flag = bool(product.get("eligible", False))
    opening_flag = bool(product.get("opening_requirements_met", False))
    item["eligible"] = eligibility_flag and opening_flag
    if not eligibility_flag:
        item["errors"].append("product eligibility is not confirmed")
    if not opening_flag:
        item["errors"].append("opening or required-balance requirements are not confirmed")
    try:
        policy = product["foreign_atm_fee"]
        if not isinstance(policy, dict):
            raise ValueError("foreign_atm_fee must be an object")
        cap = dec(product.get("operator_rebate_monthly_cap", "0"), "operator_rebate_monthly_cap")
        maintenance = dec(product.get("monthly_maintenance_fee", "0"), "monthly_maintenance_fee")
        waived = bool(product.get("maintenance_waived", False))
        limit_raw = product.get("daily_atm_limit")
        limit = None if limit_raw is None else dec(limit_raw, "daily_atm_limit")
        markup = dec(product.get("currency_conversion_markup_percent", "0"), "currency_conversion_markup_percent")

        bank_total = ZERO
        gross_operator = ZERO
        rebate_total = ZERO
        withdrawal_total = ZERO
        limit_warnings = []
        for month_no, withdrawals in enumerate(months, 1):
            free_left = 0
            if policy.get("type") == "free_allowance_then_flat":
                raw_free = policy.get("free_withdrawals")
                if not isinstance(raw_free, int) or raw_free < 0:
                    raise ValueError("foreign_atm_fee.free_withdrawals must be a nonnegative integer")
                free_left = raw_free
            month_operator = ZERO
            for withdrawal_no, (amount, operator_fee) in enumerate(withdrawals, 1):
                withdrawal_total += amount
                if limit is not None and amount > limit:
                    limit_warnings.append(f"month {month_no}, withdrawal {withdrawal_no} exceeds daily ATM limit")
                if free_left:
                    free_left -= 1
                else:
                    bank_total += fee_for_withdrawal(amount, policy)
                if operator_fee is not None:
                    month_operator += operator_fee
            if operators_known:
                gross_operator += month_operator
                rebate_total += min(month_operator, cap)

        if daily_totals is None:
            if limit is not None:
                item["warnings"].append("daily withdrawal grouping was not supplied; aggregate daily-limit compliance is unconfirmed")
        elif limit is not None:
            for month_no, days in enumerate(daily_totals, 1):
                for day_no, daily_amount in enumerate(days, 1):
                    if daily_amount > limit:
                        limit_warnings.append(f"month {month_no}, day {day_no} total exceeds daily ATM limit")

        maintenance_total = ZERO if waived else maintenance * len(months)
        conversion_total = withdrawal_total * markup / 100
        known_base = bank_total + maintenance_total + conversion_total
        item.update({
            "withdrawal_amount_total": fmt(withdrawal_total),
            "bank_foreign_atm_fees": fmt(bank_total),
            "maintenance_fees": fmt(maintenance_total),
            "currency_conversion_markup_percent": str(markup),
            "currency_conversion_markup_cost": fmt(conversion_total),
            "maximum_documented_operator_rebate": fmt(cap * len(months)),
            "daily_limit_warnings": limit_warnings,
        })
        if operators_known:
            net_operator = gross_operator - rebate_total
            item.update({
                "operator_fees_before_rebates": fmt(gross_operator),
                "operator_fee_rebates": fmt(rebate_total),
                "net_operator_fees": fmt(net_operator),
                "total_known_cost": fmt(known_base + net_operator),
                "total_cost_known": True,
            })
        else:
            item.update({
                "operator_fees_before_rebates": None,
                "operator_fee_rebates": None,
                "net_operator_fees": None,
                "total_known_cost": fmt(known_base),
                "total_cost_known": False,
            })
            item["warnings"].append("third-party operator fees are unknown; final total cost cannot be calculated")
    except (KeyError, TypeError, ValueError) as exc:
        item["errors"].append(str(exc))
    return item


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level JSON value must be an object")
    months, operators_known = parse_months(payload.get("months"))
    daily_totals = parse_daily_totals(payload.get("daily_totals"), len(months))
    products = payload.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty list")
    return {
        "errors": [],
        "operator_fees_known": operators_known,
        "month_count": len(months),
        "withdrawal_count": sum(len(month) for month in months),
        "products": [product_result(product, months, operators_known, daily_totals) for product in products],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"errors": [str(exc)], "products": []}, separators=(",", ":")))
