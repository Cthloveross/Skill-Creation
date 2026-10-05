#!/usr/bin/env python3
"""Calculate documented scheduled bank fees for travel ATM candidates.

Reads JSON from stdin and writes JSON to stdout.  It never calls banking tools.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def nonnegative_money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal number")
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def nonnegative_int(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a nonnegative integer")
    if result < 0 or str(result) != str(value):
        raise ValueError(f"{field} must be a nonnegative integer")
    return result


def component_monthly_cost(component, withdrawals_per_month, withdrawal_amount):
    kind = component.get("kind")
    if kind == "flat":
        amount = nonnegative_money(component.get("amount"), "flat.amount")
        return amount * withdrawals_per_month
    if kind == "percent_min":
        rate = nonnegative_money(component.get("rate"), "percent_min.rate")
        minimum = nonnegative_money(component.get("minimum"), "percent_min.minimum")
        return max(withdrawal_amount * rate, minimum) * withdrawals_per_month
    if kind == "percent_max":
        rate = nonnegative_money(component.get("rate"), "percent_max.rate")
        maximum = nonnegative_money(component.get("maximum"), "percent_max.maximum")
        return min(withdrawal_amount * rate, maximum) * withdrawals_per_month
    if kind == "allowance_flat":
        free = nonnegative_int(component.get("free_per_month"), "allowance_flat.free_per_month")
        amount = nonnegative_money(component.get("amount"), "allowance_flat.amount")
        return amount * max(0, withdrawals_per_month - free)
    raise ValueError(f"unsupported ATM fee component kind: {kind}")


def calculate_candidate(candidate, months, withdrawals_per_month, withdrawal_amount):
    if not isinstance(candidate, dict):
        raise ValueError("each candidate must be an object")
    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("candidate.name must be a nonempty string")
    maintenance = nonnegative_money(
        candidate.get("monthly_maintenance_fee", "0"),
        "monthly_maintenance_fee",
    )
    waived = candidate.get("maintenance_waived")
    if not isinstance(waived, bool):
        raise ValueError("maintenance_waived must be boolean")
    components = candidate.get("atm_fee_components", [])
    if not isinstance(components, list):
        raise ValueError("atm_fee_components must be an array")

    maintenance_total = Decimal("0") if waived else maintenance * months
    monthly_atm_total = sum(
        (component_monthly_cost(component, withdrawals_per_month, withdrawal_amount)
         for component in components),
        Decimal("0"),
    )
    atm_total = monthly_atm_total * months
    warnings = [
        "Third-party ATM operator surcharges and rebates are excluded from this total."
    ]
    if "daily_atm_limit" in candidate and candidate["daily_atm_limit"] is not None:
        limit = nonnegative_money(candidate["daily_atm_limit"], "daily_atm_limit")
        if withdrawal_amount > limit:
            warnings.append("One planned withdrawal exceeds the documented daily ATM limit.")
        else:
            warnings.append(
                "The individual withdrawal is within the stated daily limit; multiple "
                "withdrawals on one day require a separate daily-total check."
            )

    return {
        "name": name,
        "monthly_maintenance_total": str(money(maintenance_total)),
        "atm_fee_total": str(money(atm_total)),
        "scheduled_bank_fee_total": str(money(maintenance_total + atm_total)),
        "warnings": warnings,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        months = nonnegative_int(payload.get("months"), "months")
        if months == 0:
            raise ValueError("months must be greater than zero")
        withdrawals_per_month = nonnegative_int(
            payload.get("withdrawals_per_month"), "withdrawals_per_month"
        )
        withdrawal_amount = nonnegative_money(
            payload.get("withdrawal_amount"), "withdrawal_amount"
        )
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("candidates must be a nonempty array")
        results = [
            calculate_candidate(c, months, withdrawals_per_month, withdrawal_amount)
            for c in candidates
        ]
        results.sort(key=lambda row: (Decimal(row["scheduled_bank_fee_total"]), row["name"]))
        output = {
            "valid": True,
            "assumptions": {
                "months": months,
                "withdrawals_per_month": withdrawals_per_month,
                "withdrawal_amount": str(money(withdrawal_amount)),
                "operator_surcharges_included": False,
                "rebates_included": False,
            },
            "results": results,
        }
    except (ValueError, TypeError, InvalidOperation, json.JSONDecodeError) as exc:
        output = {"valid": False, "errors": [str(exc)]}
    sys.stdout.write(json.dumps(output, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
