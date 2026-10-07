#!/usr/bin/env python3
"""Reconcile established, posted ATM bank-fee entries for one account/month.

Input is deliberately normalized by the reviewer: this tool does not infer network,
foreign status, fee-to-withdrawal links, or whether an unrelated credit is a bank-fee
correction. It calculates expected bank fees and a conservative correction amount.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

# Reuse the product rules and money handling rather than duplicate them.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from calculate_atm_fees import VALID_KINDS, VALID_PRODUCTS, expected_fee, money, parse_amount

CENT = Decimal("0.01")


def positive(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a positive decimal")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a positive decimal")
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{label} must be a positive decimal")
    return parsed.quantize(CENT, rounding=ROUND_HALF_UP)


def require_id(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def calculate(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    product = payload.get("account_product")
    withdrawals = payload.get("withdrawals")
    fees = payload.get("fee_entries", [])
    credits = payload.get("prior_corrections", [])
    if product not in VALID_PRODUCTS:
        raise ValueError("account_product must be purple, light_blue, dark_green, or evergreen")
    if not isinstance(withdrawals, list) or not isinstance(fees, list) or not isinstance(credits, list):
        raise ValueError("withdrawals, fee_entries, and prior_corrections must be arrays")

    usage = {"out_of_network": 0, "foreign": 0}
    rows = {}
    for index, item in enumerate(withdrawals):
        if not isinstance(item, dict):
            raise ValueError(f"withdrawals[{index}] must be an object")
        wid = require_id(item.get("withdrawal_id"), f"withdrawals[{index}].withdrawal_id")
        if wid in rows:
            raise ValueError("withdrawal_id values must be unique")
        if item.get("status") != "posted":
            raise ValueError(f"withdrawals[{index}] must be posted")
        kind = item.get("kind")
        if kind not in VALID_KINDS:
            raise ValueError(f"withdrawals[{index}].kind must be in_network, out_of_network, or foreign")
        amount = parse_amount(item.get("amount"), index)
        expected, rule = expected_fee(product, kind, amount, usage)
        rows[wid] = {"withdrawal_id": wid, "expected": expected.quantize(CENT), "fees": Decimal("0"),
                     "credits": Decimal("0"), "rule": rule}

    def add_entries(entries, field, prefix):
        seen = set()
        for index, item in enumerate(entries):
            if not isinstance(item, dict):
                raise ValueError(f"{prefix}[{index}] must be an object")
            entry_id = require_id(item.get("entry_id"), f"{prefix}[{index}].entry_id")
            if entry_id in seen:
                raise ValueError(f"{prefix} entry_id values must be unique")
            seen.add(entry_id)
            wid = require_id(item.get("withdrawal_id"), f"{prefix}[{index}].withdrawal_id")
            if wid not in rows:
                raise ValueError(f"{prefix}[{index}] references an unknown withdrawal_id")
            if item.get("status") != "posted":
                raise ValueError(f"{prefix}[{index}] must be posted")
            rows[wid][field] += positive(item.get("amount"), f"{prefix}[{index}].amount")

    add_entries(fees, "fees", "fee_entries")
    add_entries(credits, "credits", "prior_corrections")

    result_rows = []
    total = Decimal("0")
    for row in rows.values():
        # A prior correction is subtracted only after the reviewer has established
        # that it corrects this bank-fee item; third-party/operator rebates must not
        # be included in prior_corrections.
        net_overcharge = row["fees"] - row["credits"] - row["expected"]
        correction = max(net_overcharge, Decimal("0")).quantize(CENT)
        total += correction
        result_rows.append({
            "withdrawal_id": row["withdrawal_id"],
            "expected_bank_fee": money(row["expected"]),
            "posted_bank_fee_total": money(row["fees"]),
            "documented_prior_correction_total": money(row["credits"]),
            "fee_refund_due": money(correction),
            "rule": row["rule"],
        })
    return {"account_product": product, "items": result_rows,
            "total_fee_refund_due": money(total),
            "limitations": [
                "All withdrawals must already be in chronological order and have an established classification.",
                "Use only posted, mapped bank-fee entries.",
                "Include a prior correction only when records prove it corrects that same bank-fee item; exclude operator-surcharge rebates.",
                "This does not establish Purple operator-fee rebate eligibility."
            ]}


def main():
    try:
        print(json.dumps(calculate(json.load(sys.stdin)), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
