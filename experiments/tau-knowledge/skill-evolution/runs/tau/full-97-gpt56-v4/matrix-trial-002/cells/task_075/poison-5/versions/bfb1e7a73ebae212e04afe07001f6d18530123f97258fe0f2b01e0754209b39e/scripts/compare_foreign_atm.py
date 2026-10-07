#!/usr/bin/env python3
"""Compare documented foreign-ATM bank fees.

Reads one JSON object from stdin and writes one JSON object to stdout.
See SKILL.md for the input schema. This script only calculates; it does not
perform banking actions.
"""
import json
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def decimal_value(value, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number, not a boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid decimal number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative finite number")
    return result


def positive_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def per_withdrawal_percent(amount: Decimal, rate: Decimal, minimum: Decimal) -> Decimal:
    return max(amount * rate, minimum)


def operator_result(months: int, withdrawals_per_month: int, data: dict, cap: Decimal):
    if "operator_fee_per_withdrawal" in data:
        fee = decimal_value(data["operator_fee_per_withdrawal"], "operator_fee_per_withdrawal")
        totals = [fee * withdrawals_per_month for _ in range(months)]
    elif "operator_fee_totals_by_month" in data:
        supplied = data["operator_fee_totals_by_month"]
        if not isinstance(supplied, list) or len(supplied) != months:
            raise ValueError("operator_fee_totals_by_month must be a list with one total for each month")
        totals = [decimal_value(item, "operator_fee_totals_by_month item") for item in supplied]
    else:
        return {
            "known": False,
            "formula": "sum over each month of max(monthly eligible operator fees - monthly rebate cap, 0)",
            "monthly_rebate_cap": money(cap),
        }

    remainder = sum((max(total - cap, Decimal("0")) for total in totals), Decimal("0"))
    rebated = sum((min(total, cap) for total in totals), Decimal("0"))
    return {
        "known": True,
        "operator_fee_total_before_rebates": money(sum(totals, Decimal("0"))),
        "eligible_operator_fees_rebated": money(rebated),
        "third_party_out_of_pocket": money(remainder),
        "monthly_rebate_cap": money(cap),
    }


def no_rebate_operator_result(months: int, withdrawals_per_month: int, data: dict):
    if "operator_fee_per_withdrawal" in data:
        fee = decimal_value(data["operator_fee_per_withdrawal"], "operator_fee_per_withdrawal")
        total = fee * months * withdrawals_per_month
        return {"known": True, "third_party_out_of_pocket": money(total), "monthly_rebate_cap": "0.00"}
    if "operator_fee_totals_by_month" in data:
        supplied = data["operator_fee_totals_by_month"]
        if not isinstance(supplied, list) or len(supplied) != months:
            raise ValueError("operator_fee_totals_by_month must be a list with one total for each month")
        total = sum((decimal_value(item, "operator_fee_totals_by_month item") for item in supplied), Decimal("0"))
        return {"known": True, "third_party_out_of_pocket": money(total), "monthly_rebate_cap": "0.00"}
    return {"known": False, "formula": "sum of actual third-party ATM operator fees", "monthly_rebate_cap": "0.00"}


def add_product(name, bank_fee: Decimal, operator, notes, output):
    row = {
        "account": name,
        "known_bank_fee_for_trip": money(bank_fee),
        "operator_fee_treatment": operator,
        "notes": notes,
    }
    if operator["known"]:
        combined = bank_fee + Decimal(operator["third_party_out_of_pocket"])
        row["combined_known_components"] = money(combined)
    output.append(row)


def main(data: dict):
    months = positive_int(data.get("months"), "months")
    withdrawals = positive_int(data.get("withdrawals_per_month"), "withdrawals_per_month")
    amount = decimal_value(data.get("withdrawal_amount_usd"), "withdrawal_amount_usd")
    if amount <= 0:
        raise ValueError("withdrawal_amount_usd must be greater than zero")
    if "operator_fee_per_withdrawal" in data and "operator_fee_totals_by_month" in data:
        raise ValueError("supply only one operator-fee input method")

    count = months * withdrawals
    products = []

    bluest_ops = operator_result(months, withdrawals, data, Decimal("50"))
    add_product(
        "Bluest Account", Decimal("0"), bluest_ops,
        ["No Rho-Bank foreign ATM withdrawal fee.",
         "Conditional: a $75,000 opening deposit is required; retaining benefits requires a $112,500 daily balance; a $75 monthly maintenance fee applies below that balance."], products)

    purple_ops = operator_result(months, withdrawals, data, Decimal("30"))
    purple_oof = Decimal("2.50") * count
    purple = {
        "account": "Purple Account",
        "stated_foreign_atm_bank_fee_for_trip": money(Decimal("0")),
        "out_of_network_scenario_bank_fee_for_trip": money(purple_oof),
        "operator_fee_treatment": purple_ops,
        "notes": [
            "Documentation states a $0 foreign ATM withdrawal fee.",
            "Separate documentation charges $2.50 per out-of-network ATM withdrawal and does not establish whether a foreign ATM will be treated as out-of-network.",
            "Do not collapse these two interpretations into one guaranteed bank-fee total."
        ],
    }
    if purple_ops["known"]:
        remainder = Decimal(purple_ops["third_party_out_of_pocket"])
        purple["combined_components_stated_foreign_fee"] = money(remainder)
        purple["combined_components_out_of_network_scenario"] = money(purple_oof + remainder)
    products.append(purple)

    light_blue_fee = Decimal(max(withdrawals - 2, 0)) * Decimal("4") * months
    add_product(
        "Light Blue Account", light_blue_fee, no_rebate_operator_result(months, withdrawals, data),
        ["Two free foreign ATM withdrawals reset each month; each further foreign withdrawal that month costs $4."], products)

    blue_green_each = per_withdrawal_percent(amount, Decimal("0.03"), Decimal("5"))
    for name in ("Blue Account", "Green Account (checking)"):
        add_product(
            name, blue_green_each * count, no_rebate_operator_result(months, withdrawals, data),
            ["Bank fee is the greater of 3% of each withdrawal's USD equivalent or $5, calculated per withdrawal."], products)

    evergreen_each = per_withdrawal_percent(amount, Decimal("0.02"), Decimal("3"))
    add_product(
        "Evergreen Account", evergreen_each * count, no_rebate_operator_result(months, withdrawals, data),
        ["Bank fee is the greater of 2% of each withdrawal's USD equivalent or $3, calculated per withdrawal."], products)

    return {
        "assumptions": {
            "months": months,
            "withdrawals_per_month": withdrawals,
            "total_withdrawals": count,
            "withdrawal_amount_usd": money(amount),
            "third_party_operator_fees_are": "provided" if ("operator_fee_per_withdrawal" in data or "operator_fee_totals_by_month" in data) else "unknown",
        },
        "products": products,
        "warnings": [
            "Third-party ATM operator charges are separate from bank fees and may vary by machine.",
            "Rebates are modeled only against eligible operator fees and reset by month.",
            "Daily withdrawal limits concern withdrawals in a 24-hour period; this monthly plan alone cannot establish compliance with a daily limit."
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
