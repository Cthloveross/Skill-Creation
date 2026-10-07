#!/usr/bin/env python3
"""Calculate a savings-interest discrepancy from verified statement inputs.

Reads one JSON object from stdin and writes one JSON object to stdout.  This helper
is deliberately side-effect free: it does not access banking systems or recommend
a credit unless the arithmetic input itself is complete.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
ZERO = Decimal("0")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def numeric_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    values = [decimal_value(item, field) for item in value]
    if any(item < ZERO for item in values):
        raise ValueError(f"{field} cannot contain negative values")
    return values


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def output_error(errors):
    return {"decision": "insufficient_data", "errors": errors}


def calculate(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    required = ["base_apy", "daily_balances", "actual_interest"]
    absent = [field for field in required if field not in data]
    if absent:
        return output_error(["missing required field(s): " + ", ".join(absent)])

    base = decimal_value(data["base_apy"], "base_apy")
    if base < ZERO:
        raise ValueError("base_apy cannot be negative")
    checking = numeric_list(data.get("checking_boosts", []), "checking_boosts")
    cards = numeric_list(data.get("card_bonuses", []), "card_bonuses")
    others = numeric_list(data.get("other_bonuses", []), "other_bonuses")
    actual_interest = decimal_value(data["actual_interest"], "actual_interest")
    if actual_interest < ZERO:
        raise ValueError("actual_interest cannot be negative")

    days_in_year = decimal_value(data.get("days_in_year", 365), "days_in_year")
    if days_in_year <= ZERO or days_in_year != days_in_year.to_integral_value():
        raise ValueError("days_in_year must be a positive whole number")
    rows = data["daily_balances"]
    if not isinstance(rows, list) or not rows:
        return output_error(["daily_balances must be a nonempty list"])

    selected_checking = max(checking, default=ZERO)
    selected_card = max(cards, default=ZERO)
    expected_apy = base + selected_checking + selected_card + sum(others, ZERO)
    annual_rate = expected_apy / Decimal("100")
    expected_raw = ZERO
    total_days = 0
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or "balance" not in row or "days" not in row:
            raise ValueError(f"daily_balances[{index}] needs balance and days")
        balance = decimal_value(row["balance"], f"daily_balances[{index}].balance")
        days = decimal_value(row["days"], f"daily_balances[{index}].days")
        if balance < ZERO:
            raise ValueError(f"daily_balances[{index}].balance cannot be negative")
        if days <= ZERO or days != days.to_integral_value():
            raise ValueError(f"daily_balances[{index}].days must be a positive whole number")
        day_count = int(days)
        # APY is an effective annual rate. Convert it to a daily compounded rate.
        expected_raw += balance * ((Decimal("1") + annual_rate) ** (days / days_in_year) - Decimal("1"))
        total_days += day_count

    expected_interest = money(expected_raw)
    credit = money(max(expected_interest - money(actual_interest), ZERO))
    result = {
        "decision": "credit_eligible" if credit > ZERO else "no_credit",
        "base_apy": str(base),
        "selected_checking_boost": str(selected_checking),
        "selected_card_bonus": str(selected_card),
        "other_bonuses_total": str(sum(others, ZERO)),
        "expected_apy": str(expected_apy),
        "total_days": total_days,
        "expected_interest": format(expected_interest, ".2f"),
        "actual_interest": format(money(actual_interest), ".2f"),
        "credit_amount": format(credit, ".2f"),
    }
    if "actual_apy" in data and data["actual_apy"] is not None:
        actual_apy = decimal_value(data["actual_apy"], "actual_apy")
        if actual_apy < ZERO:
            raise ValueError("actual_apy cannot be negative")
        result["actual_apy"] = str(actual_apy)
    else:
        result["actual_apy"] = None
        result["report_ready"] = False
        result["report_requirement"] = "actual_apy is required before submitting a discrepancy report"
    if result.get("actual_apy") is not None:
        result["report_ready"] = credit > ZERO
    return result


def main():
    try:
        data = json.load(sys.stdin)
        result = calculate(data)
    except json.JSONDecodeError:
        result = output_error(["stdin must contain valid JSON"])
    except ValueError as exc:
        result = output_error([str(exc)])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
