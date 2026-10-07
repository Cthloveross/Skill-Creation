#!/usr/bin/env python3
"""Calculate documented ATM bank fees for one product and calendar month.

Read a JSON object from stdin and emit a JSON object to stdout. See SKILL.md for
schema and important limitations. This program intentionally does not match posted
transactions, infer ATM classifications, or decide operator-fee rebate eligibility.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
VALID_PRODUCTS = {"purple", "light_blue", "dark_green", "evergreen"}
VALID_KINDS = {"out_of_network", "foreign"}


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_amount(value, index: int) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"withdrawals[{index}].amount must be a positive decimal")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"withdrawals[{index}].amount must be a positive decimal")
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"withdrawals[{index}].amount must be a positive decimal")
    return amount


def expected_fee(product: str, kind: str, amount: Decimal, usage: dict) -> tuple[Decimal, str]:
    if product == "purple":
        if kind == "foreign":
            return Decimal("0"), "Purple foreign ATM withdrawal bank fee is $0.00"
        return Decimal("2.50"), "Purple out-of-network bank fee is $2.50 per withdrawal"

    if product == "light_blue":
        # The two documented allowances are distinct schedules. The caller must
        # supply one established classification for each withdrawal.
        count = usage[kind]
        usage[kind] += 1
        if count < 2:
            return Decimal("0"), f"Light Blue {kind} withdrawal {count + 1} of 2 is free"
        rate = Decimal("4.00") if kind == "foreign" else Decimal("2.50")
        return rate, f"Light Blue {kind} withdrawal exceeds the monthly 2-withdrawal allowance"

    if product == "dark_green":
        if kind == "foreign":
            return min(amount * Decimal("0.025"), Decimal("6.00")), "Dark Green foreign fee is 2.5%, capped at $6.00"
        return max(amount * Decimal("0.01"), Decimal("1.50")), "Dark Green out-of-network fee is 1%, $1.50 minimum"

    # evergreen
    if kind == "foreign":
        return max(amount * Decimal("0.02"), Decimal("3.00")), "Evergreen foreign fee is 2%, $3.00 minimum"
    return min(amount * Decimal("0.01"), Decimal("2.50")), "Evergreen out-of-network fee is 1%, capped at $2.50"


def calculate(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    product = payload.get("account_product")
    withdrawals = payload.get("withdrawals")
    if product not in VALID_PRODUCTS:
        raise ValueError("account_product must be purple, light_blue, dark_green, or evergreen")
    if not isinstance(withdrawals, list):
        raise ValueError("withdrawals must be an array")

    usage = {"out_of_network": 0, "foreign": 0}
    results = []
    total = Decimal("0")
    for index, withdrawal in enumerate(withdrawals):
        if not isinstance(withdrawal, dict):
            raise ValueError(f"withdrawals[{index}] must be an object")
        kind = withdrawal.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(f"withdrawals[{index}].kind must be out_of_network or foreign")
        amount = parse_amount(withdrawal.get("amount"), index)
        fee, rule = expected_fee(product, kind, amount, usage)
        fee = fee.quantize(CENT, rounding=ROUND_HALF_UP)
        total += fee
        results.append({
            "index": index,
            "amount": money(amount),
            "kind": kind,
            "expected_fee": money(fee),
            "rule": rule,
        })

    return {
        "account_product": product,
        "withdrawals": results,
        "total_expected_fee": money(total),
        "limitations": [
            "Expected fees cover only the bank fee described by the product schedule.",
            "Third-party operator surcharges are excluded.",
            "Purple operator-fee rebate eligibility requires transaction coding, posting review, and the $30 monthly cap.",
        ],
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(calculate(payload), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
