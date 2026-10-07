#!/usr/bin/env python3
"""Estimate documented travel costs for Blue and Purple checking accounts.

Reads one JSON object from stdin and writes one JSON object to stdout.
This helper performs no banking actions and intentionally excludes unknown
third-party ATM operator surcharges.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def decimal_field(payload, name, *, positive=False):
    if name not in payload:
        raise ValueError("missing required field: " + name)
    try:
        value = Decimal(str(payload[name]))
    except (InvalidOperation, ValueError):
        raise ValueError(name + " must be numeric")
    if not value.is_finite() or value < 0 or (positive and value == 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(name + " must be " + qualifier)
    return value


def boolean_field(payload, name, default=False):
    value = payload.get(name, default)
    if not isinstance(value, bool):
        raise ValueError(name + " must be a boolean")
    return value


def main():
    schema = {
        "required": {
            "months": "positive number",
            "withdrawals_per_month": "nonnegative number",
            "withdrawal_amount_usd": "nonnegative number",
        },
        "optional": {
            "can_maintain_blue_waiver_balance": "boolean; default false",
            "can_maintain_purple_waiver_balance": "boolean; default false",
            "requires_two_day_early_deposit": "boolean; default false",
        },
    }
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        months = decimal_field(payload, "months", positive=True)
        withdrawals = decimal_field(payload, "withdrawals_per_month")
        amount = decimal_field(payload, "withdrawal_amount_usd")
        blue_waiver = boolean_field(payload, "can_maintain_blue_waiver_balance")
        purple_waiver = boolean_field(payload, "can_maintain_purple_waiver_balance")
        requires_two_days = boolean_field(payload, "requires_two_day_early_deposit")

        # Blue foreign ATM charge: 1%, capped at $3, per withdrawal.
        blue_fee_each = min(amount * Decimal("0.01"), Decimal("3.00"))
        blue_atm = money(months * withdrawals * blue_fee_each)
        blue_monthly = Decimal("0") if blue_waiver else months * Decimal("20.00")
        blue_total = money(blue_atm + blue_monthly)

        # Purple has no Rho foreign ATM fee. Unknown operator fees are not
        # invented; the documented rebate can be described only as a cap.
        purple_monthly = Decimal("0") if purple_waiver else months * Decimal("15.00")
        purple_total = money(purple_monthly)

        result = {
            "validation": {"valid": True, "errors": []},
            "input_schema": schema,
            "assumptions": [
                "Estimates include documented Rho-Bank foreign ATM fees and monthly maintenance fees only.",
                "Third-party ATM operator surcharges are excluded because their amounts are not supplied.",
                "Purple may rebate eligible posted operator fees up to $30 per month; this is a cap, not an assumed credit.",
            ],
            "options": {
                "Blue Account": {
                    "early_direct_deposit_days": 1,
                    "foreign_atm_fee_per_withdrawal_usd": str(money(blue_fee_each)),
                    "estimated_rho_atm_fees_usd": str(blue_atm),
                    "estimated_maintenance_fees_usd": str(money(blue_monthly)),
                    "estimated_documented_cost_usd": str(blue_total),
                    "maintenance_fee_waived": blue_waiver,
                    "meets_two_day_early_deposit_requirement": False,
                },
                "Purple Account": {
                    "early_direct_deposit_days": 2,
                    "estimated_rho_atm_fees_usd": "0.00",
                    "estimated_maintenance_fees_usd": str(money(purple_monthly)),
                    "estimated_documented_cost_before_unknown_operator_fees_usd": str(purple_total),
                    "maintenance_fee_waived": purple_waiver,
                    "operator_fee_rebate_cap_per_month_usd": "30.00",
                    "meets_two_day_early_deposit_requirement": True,
                },
            },
            "recommendation_note": (
                "Purple Account is the only documented option in this comparison "
                "with up to two days of early direct deposit."
                if requires_two_days
                else "Compare estimates with the customer's early-deposit and balance requirements."
            ),
        }
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "validation": {"valid": False, "errors": [str(exc)]},
            "input_schema": schema,
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
