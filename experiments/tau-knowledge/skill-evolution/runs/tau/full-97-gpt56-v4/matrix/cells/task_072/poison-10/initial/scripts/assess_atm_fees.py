#!/usr/bin/env python3
"""Preliminary ATM-fee arithmetic helper. Reads JSON stdin and writes JSON stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value, field, index):
    if value is None:
        return ZERO
    if isinstance(value, bool):
        raise ValueError(f"entries[{index}].{field} must be a nonnegative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"entries[{index}].{field} must be a nonnegative decimal")
    if not result.is_finite() or result < ZERO:
        raise ValueError(f"entries[{index}].{field} must be a nonnegative decimal")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def error(message):
    return {"status": "needs_more_information", "error": message}


def main(payload):
    if not isinstance(payload, dict):
        return error("input must be a JSON object")
    product = payload.get("product")
    if product not in {"bluest", "light_green"}:
        return error("product must be 'bluest' or 'light_green'")
    if not isinstance(payload.get("statement_cycle"), str) or not payload["statement_cycle"].strip():
        return error("statement_cycle is required and must identify one cycle")
    if payload.get("benefits_active") is not True:
        return error("benefits_active must be true based on authoritative account information")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return error("entries must be a nonempty list from one statement cycle")

    prepared = []
    sequences = set()
    try:
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                return error(f"entries[{i}] must be an object")
            sequence = entry.get("sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence in sequences:
                return error("each entry requires a unique integer chronological sequence")
            sequences.add(sequence)
            foreign = entry.get("is_foreign")
            if not isinstance(foreign, bool):
                return error(f"entries[{i}].is_foreign must be true or false")
            prepared.append({
                "index": i,
                "sequence": sequence,
                "is_foreign": foreign,
                "withdrawal_amount": money(entry.get("withdrawal_amount"), "withdrawal_amount", i),
                "rho_bank_fee": money(entry.get("rho_bank_fee"), "rho_bank_fee", i),
                "third_party_fee": money(entry.get("third_party_fee"), "third_party_fee", i),
                "rebate_credit": money(entry.get("rebate_credit"), "rebate_credit", i),
            })
    except ValueError as exc:
        return error(str(exc))

    prepared.sort(key=lambda item: item["sequence"])
    if product == "bluest":
        eligible_fees = sum((x["third_party_fee"] for x in prepared), ZERO)
        posted_credits = sum((x["rebate_credit"] for x in prepared), ZERO)
        maximum_entitlement = min(eligible_fees, Decimal("50.00"))
        potential_missing = max(ZERO, maximum_entitlement - posted_credits)
        status = "no_preliminary_discrepancy" if potential_missing == ZERO else "preliminary_discrepancy"
        return {
            "status": status,
            "product": product,
            "statement_cycle": payload["statement_cycle"],
            "assumptions": [
                "All entries are in one monthly statement cycle.",
                "third_party_fee values are eligible third-party ATM fees.",
                "rebate_credit values are confirmed posted ATM rebate credits for this cycle.",
                "Benefits were active for this cycle."
            ],
            "totals": {
                "eligible_third_party_fees": fmt(eligible_fees),
                "maximum_rebate_under_50_cap": fmt(maximum_entitlement),
                "confirmed_posted_rebate_credits": fmt(posted_credits),
                "potential_missing_rebate": fmt(potential_missing)
            },
            "warning": "This is a preliminary cap calculation, not credit authorization. Verify account status, eligibility, and transaction history."
        }

    domestic_count = 0
    comparisons = []
    has_discrepancy = False
    for item in prepared:
        if item["is_foreign"]:
            amount = item["withdrawal_amount"]
            if amount <= Decimal("100.00"):
                expected = Decimal("2.00")
            elif amount <= Decimal("300.00"):
                expected = Decimal("3.50")
            else:
                expected = Decimal("5.00")
            rule = "foreign tiered Rho-Bank fee"
        else:
            domestic_count += 1
            expected = ZERO if domestic_count <= 4 else Decimal("1.50")
            rule = "domestic out-of-network monthly free-withdrawal rule"
        difference = item["rho_bank_fee"] - expected
        if difference != ZERO:
            has_discrepancy = True
        comparisons.append({
            "sequence": item["sequence"],
            "rule": rule,
            "expected_rho_bank_fee": fmt(expected),
            "reported_rho_bank_fee": fmt(item["rho_bank_fee"]),
            "reported_minus_expected": fmt(difference),
            "third_party_operator_fee_not_assessed": fmt(item["third_party_fee"])
        })
    return {
        "status": "preliminary_discrepancy" if has_discrepancy else "no_preliminary_discrepancy",
        "product": product,
        "statement_cycle": payload["statement_cycle"],
        "assumptions": [
            "All entries are in one monthly statement cycle and are in chronological sequence.",
            "Each reported Rho-Bank fee is correctly distinguished from an ATM-operator surcharge.",
            "Foreign tiered fees are assessed separately from domestic out-of-network counting.",
            "Benefits and Light Green eligibility were active for this cycle."
        ],
        "entries": comparisons,
        "warning": "A preliminary discrepancy requires authoritative transaction-history and account-eligibility verification before any fee refund."
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps(error("stdin must contain valid JSON"), separators=(",", ":")))
        sys.exit(0)
    print(json.dumps(main(payload), separators=(",", ":")))
