#!/usr/bin/env python3
"""Calculate documented ATM bank fees and Purple operator-fee rebate caps.

Reads one JSON object from stdin and emits one JSON object on stdout.
This utility only performs arithmetic; callers must establish all banking facts.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value, field, allow_zero=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a decimal amount")
    if not result.is_finite() or result < 0 or (result == 0 and not allow_zero):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{field} must be a finite {qualifier} amount")
    return result


def fmt(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def nonnegative_int(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a nonnegative integer")
    if parsed < 0 or str(parsed) != str(value).strip():
        raise ValueError(f"{field} must be a nonnegative integer")
    return parsed


def calculate(product, scope, amount, prior_count):
    if product == "purple":
        if scope == "domestic_out_of_network":
            return Decimal("2.50"), "$2.50 per domestic out-of-network withdrawal"
        return Decimal("0"), "$0 foreign ATM withdrawal fee"
    if product == "light_blue":
        if prior_count is None:
            raise ValueError("prior_withdrawal_count is required for light_blue")
        if prior_count < 2:
            return Decimal("0"), "within the first two free monthly withdrawals for this category"
        if scope == "domestic_out_of_network":
            return Decimal("2.50"), "$2.50 after two free monthly out-of-network withdrawals"
        return Decimal("4.00"), "$4.00 after two free monthly foreign withdrawals"
    if product == "dark_green":
        if scope == "domestic_out_of_network":
            return max(amount * Decimal("0.01"), Decimal("1.50")), "1% with a $1.50 minimum"
        return min(amount * Decimal("0.025"), Decimal("6.00")), "2.5% with a $6.00 maximum"
    if product == "evergreen":
        if scope == "domestic_out_of_network":
            return min(amount * Decimal("0.01"), Decimal("2.50")), "1% with a $2.50 maximum"
        return max(amount * Decimal("0.02"), Decimal("3.00")), "2% with a $3.00 minimum"
    raise ValueError("product must be purple, light_blue, dark_green, or evergreen")


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    product = payload.get("product")
    scope = payload.get("scope")
    if product not in {"purple", "light_blue", "dark_green", "evergreen"}:
        raise ValueError("product must be purple, light_blue, dark_green, or evergreen")
    if scope not in {"domestic_out_of_network", "foreign"}:
        raise ValueError("scope must be domestic_out_of_network or foreign")
    amount = money(payload.get("withdrawal_amount"), "withdrawal_amount")
    prior = None
    if "prior_withdrawal_count" in payload:
        prior = nonnegative_int(payload["prior_withdrawal_count"], "prior_withdrawal_count")
    fee, rule = calculate(product, scope, amount, prior)
    output = {"expected_bank_fee": fmt(fee), "rule": rule}

    rebate_fields = {"operator_fee_amount", "prior_eligible_rebates", "operator_fee_eligible_and_posted"}
    supplied = rebate_fields.intersection(payload)
    if supplied:
        if product != "purple":
            raise ValueError("operator-fee rebate calculation is documented only for purple")
        if supplied != rebate_fields:
            raise ValueError("all Purple operator-fee rebate fields must be supplied together")
        operator_fee = money(payload["operator_fee_amount"], "operator_fee_amount", allow_zero=True)
        prior_rebates = money(payload["prior_eligible_rebates"], "prior_eligible_rebates", allow_zero=True)
        eligible = payload["operator_fee_eligible_and_posted"]
        if not isinstance(eligible, bool):
            raise ValueError("operator_fee_eligible_and_posted must be boolean")
        if prior_rebates > Decimal("30.00"):
            raise ValueError("prior_eligible_rebates cannot exceed the $30 monthly cap")
        rebate = min(operator_fee, Decimal("30.00") - prior_rebates) if eligible else Decimal("0")
        output["expected_operator_fee_rebate"] = fmt(rebate)
        output["rebate_rule"] = ("eligible posted operator fee, capped by remaining $30 monthly rebate allowance"
                                 if eligible else "no rebate calculated because eligibility and posting were not established")
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
