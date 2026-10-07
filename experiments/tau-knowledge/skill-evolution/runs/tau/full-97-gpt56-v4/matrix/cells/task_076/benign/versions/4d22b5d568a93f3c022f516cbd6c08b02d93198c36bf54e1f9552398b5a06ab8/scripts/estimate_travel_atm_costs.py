#!/usr/bin/env python3
"""Estimate documented ATM-side charges for supported travel checking options.

The program is intentionally conservative: ATM-operator surcharges are external
and unknown, and Purple's supplied foreign-ATM and out-of-network statements are
both reported rather than reconciled by assumption.  It performs no banking
operation.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_field(data, key):
    value = data.get(key)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{key} must be a non-negative number")
    if not number.is_finite() or number < 0:
        raise ValueError(f"{key} must be a non-negative number")
    return number


def main():
    try:
        data = json.load(sys.stdin)
        per_month = decimal_field(data, "withdrawals_per_month")
        withdrawal_amount = decimal_field(data, "withdrawal_amount")
        months = decimal_field(data, "months")
        if months != months.to_integral_value() or per_month != per_month.to_integral_value():
            raise ValueError("months and withdrawals_per_month must be whole numbers")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return

    total_withdrawals = per_month * months
    # Known bank fees exclude third-party operator surcharges. Rebate caps are
    # separately reported because their actual use depends on those surcharges.
    evergreen_each = max(withdrawal_amount * Decimal("0.02"), Decimal("3.00"))
    result = {
        "valid": True,
        "usage": {
            "months": int(months),
            "withdrawals_per_month": int(per_month),
            "withdrawal_amount": f"{withdrawal_amount:.2f}",
            "total_withdrawals": int(total_withdrawals),
        },
        "products": {
            "Bluest Account": {
                "known_foreign_bank_atm_fee": "0.00",
                "monthly_operator_fee_rebate_cap": "50.00",
                "trip_operator_fee_rebate_cap": f"{Decimal('50.00') * months:.2f}",
                "notes": [
                    "Operator surcharges are unknown and may remain above the cap.",
                    "Benefits require the documented ongoing balance condition to stay active.",
                    "Early direct deposit is documented as up to 2 days, not guaranteed.",
                ],
            },
            "Purple Account": {
                "stated_foreign_bank_atm_fee": "0.00",
                "possible_out_of_network_bank_fee": "2.50 per withdrawal",
                "possible_out_of_network_bank_fee_for_trip": f"{Decimal('2.50') * total_withdrawals:.2f}",
                "monthly_operator_fee_rebate_cap": "30.00",
                "trip_operator_fee_rebate_cap": f"{Decimal('30.00') * months:.2f}",
                "notes": [
                    "Do not assume overseas withdrawals are or are not out-of-network.",
                    "Operator surcharges are unknown and may remain above the cap.",
                    "Early direct deposit is documented as up to 2 days, not guaranteed.",
                ],
            },
            "Evergreen Account": {
                "foreign_bank_atm_fee_per_withdrawal": f"{evergreen_each:.2f}",
                "foreign_bank_atm_fee_for_trip": f"{evergreen_each * total_withdrawals:.2f}",
                "notes": [
                    "Fee is 2% of each withdrawal, with a $3.00 minimum.",
                    "Third-party operator surcharges may additionally apply.",
                    "Early direct deposit is documented as up to 2 days, not guaranteed.",
                ],
            },
            "Green Fee-Free Account": {
                "known_foreign_bank_atm_fee": "0.00",
                "notes": ["No early direct-deposit advance is documented."],
            },
        },
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
