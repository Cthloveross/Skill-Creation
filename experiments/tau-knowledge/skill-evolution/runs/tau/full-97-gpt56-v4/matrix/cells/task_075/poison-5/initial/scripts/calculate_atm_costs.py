#!/usr/bin/env python3
"""Calculate generic overseas ATM costs from JSON stdin and write JSON stdout."""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("0.01")


def money(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a monetary number, not boolean")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid monetary value")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
    return amount


def whole_count(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def as_money_string(value):
    return format(value.quantize(CENTS, rounding=ROUND_HALF_UP), ".2f")


def monthly_values(value, months, field, monetary=False):
    values = value if isinstance(value, list) else [value] * months
    if len(values) != months:
        raise ValueError(f"{field} list length must equal months")
    if monetary:
        return [money(item, field) for item in values]
    return [whole_count(item, field) for item in values]


def main(payload):
    months = whole_count(payload.get("months"), "months")
    if months == 0:
        raise ValueError("months must be greater than zero")
    withdrawals = monthly_values(payload.get("withdrawals_per_month"), months,
                                 "withdrawals_per_month")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty list")

    operator_raw = payload.get("operator_fees_by_month")
    operator_fees = None if operator_raw is None else monthly_values(
        operator_raw, months, "operator_fees_by_month", monetary=True
    )

    output_accounts = []
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            raise ValueError(f"accounts[{index}] must be an object")
        name = account.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"accounts[{index}].name must be a nonempty string")
        withdrawal_fee = money(account.get("out_of_network_fee"),
                               f"accounts[{index}].out_of_network_fee")
        maintenance = money(account.get("monthly_maintenance_fee_applies"),
                            f"accounts[{index}].monthly_maintenance_fee_applies")
        cap = money(account.get("operator_fee_rebate_cap"),
                    f"accounts[{index}].operator_fee_rebate_cap")

        bank_withdrawal_cost = withdrawal_fee * sum(withdrawals)
        maintenance_cost = maintenance * months
        base_cost = bank_withdrawal_cost + maintenance_cost
        result = {
            "name": name,
            "bank_withdrawal_cost": as_money_string(bank_withdrawal_cost),
            "maintenance_cost": as_money_string(maintenance_cost),
            "known_base_cost": as_money_string(base_cost),
            "operator_fee_rebate_cap_per_month": as_money_string(cap),
        }
        if operator_fees is None:
            result["operator_fee_status"] = "unknown_not_included"
        else:
            rebate = sum(min(fee, cap) for fee in operator_fees)
            unreimbursed = sum(operator_fees) - rebate
            result.update({
                "operator_fee_status": "included",
                "operator_fees_total": as_money_string(sum(operator_fees)),
                "operator_fee_rebates": as_money_string(rebate),
                "unreimbursed_operator_fees": as_money_string(unreimbursed),
                "all_in_cost": as_money_string(base_cost + unreimbursed),
            })
        output_accounts.append(result)

    return {
        "months": months,
        "withdrawals_per_month": withdrawals,
        "total_withdrawals": sum(withdrawals),
        "operator_fees_known": operator_fees is not None,
        "accounts": output_accounts,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
