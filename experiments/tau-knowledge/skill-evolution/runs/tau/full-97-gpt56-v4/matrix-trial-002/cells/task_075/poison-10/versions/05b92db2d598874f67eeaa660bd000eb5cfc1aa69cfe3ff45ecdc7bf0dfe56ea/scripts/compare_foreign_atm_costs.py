#!/usr/bin/env python3
"""Compute projected foreign-ATM bank fees from JSON stdin and emit JSON stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite() or result < ZERO:
        raise ValueError(f"{field} must be non-negative")
    return result


def whole(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a non-negative integer")
    if result < 0 or str(value).strip() not in (str(result), f"{result}.0"):
        raise ValueError(f"{field} must be a non-negative integer")
    return result


def display(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def product_cost(product, months, withdrawals, withdrawal_amount, balance, include_maintenance, surcharge):
    name = product.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each product requires a nonempty name")
    rule = product.get("foreign_atm_fee")
    if not isinstance(rule, dict):
        raise ValueError(f"{name}: foreign_atm_fee must be an object")
    kind = rule.get("kind")
    monthly_atm = ZERO
    if kind == "zero":
        pass
    elif kind == "flat":
        amount = money(rule.get("amount"), f"{name}.foreign_atm_fee.amount")
        free = whole(rule.get("free_withdrawals_per_month", 0), f"{name}.free_withdrawals_per_month")
        monthly_atm = Decimal(max(withdrawals - free, 0)) * amount
    elif kind == "percent_min":
        percent = money(rule.get("percent"), f"{name}.foreign_atm_fee.percent")
        minimum = money(rule.get("minimum"), f"{name}.foreign_atm_fee.minimum")
        per_withdrawal = max(withdrawal_amount * percent / Decimal("100"), minimum)
        monthly_atm = Decimal(withdrawals) * per_withdrawal
    else:
        raise ValueError(f"{name}: unsupported foreign_atm_fee.kind")

    atm_total = monthly_atm * months
    maintenance_total = ZERO
    waived = None
    if include_maintenance:
        maintenance = money(product.get("monthly_maintenance_fee", "0"), f"{name}.monthly_maintenance_fee")
        threshold_value = product.get("maintenance_waiver_min_daily_balance")
        waived = False
        if threshold_value is not None and balance is not None:
            threshold = money(threshold_value, f"{name}.maintenance_waiver_min_daily_balance")
            waived = balance >= threshold
        if not waived:
            maintenance_total = maintenance * months

    rebate_total = ZERO
    if surcharge is not None:
        cap = money(product.get("foreign_atm_rebate_cap_per_month", "0"), f"{name}.foreign_atm_rebate_cap_per_month")
        eligible_surcharges = Decimal(withdrawals) * surcharge
        rebate_total = min(eligible_surcharges, cap) * months

    total = max(ZERO, atm_total + maintenance_total - rebate_total)
    return {
        "name": name,
        "foreign_atm_bank_fee_total": display(atm_total),
        "maintenance_fee_total": display(maintenance_total),
        "maintenance_waived": waived,
        "estimated_operator_fee_rebate_total": display(rebate_total),
        "projected_total_cost": display(total),
    }


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    months = whole(data.get("months"), "months")
    withdrawals = whole(data.get("withdrawals_per_month"), "withdrawals_per_month")
    withdrawal_amount = money(data.get("usd_per_withdrawal"), "usd_per_withdrawal")
    products = data.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("products must be a nonempty array")
    include_maintenance = data.get("include_maintenance", True)
    if not isinstance(include_maintenance, bool):
        raise ValueError("include_maintenance must be boolean")
    balance = None
    if data.get("maintained_daily_balance") is not None:
        balance = money(data["maintained_daily_balance"], "maintained_daily_balance")
    surcharge = None
    if data.get("operator_surcharge_per_withdrawal") is not None:
        surcharge = money(data["operator_surcharge_per_withdrawal"], "operator_surcharge_per_withdrawal")

    results = [product_cost(p, months, withdrawals, withdrawal_amount, balance,
                            include_maintenance, surcharge) for p in products]
    lowest = min(Decimal(row["projected_total_cost"]) for row in results)
    lowest_names = [row["name"] for row in results
                    if Decimal(row["projected_total_cost"]) == lowest]
    return {
        "ok": True,
        "assumptions": {
            "months": months,
            "withdrawals_per_month": withdrawals,
            "usd_per_withdrawal": display(withdrawal_amount),
            "includes_maintenance": include_maintenance,
            "operator_surcharge_estimate_supplied": surcharge is not None,
        },
        "products": results,
        "lowest_projected_total_cost": display(lowest),
        "lowest_cost_product_names": lowest_names,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
