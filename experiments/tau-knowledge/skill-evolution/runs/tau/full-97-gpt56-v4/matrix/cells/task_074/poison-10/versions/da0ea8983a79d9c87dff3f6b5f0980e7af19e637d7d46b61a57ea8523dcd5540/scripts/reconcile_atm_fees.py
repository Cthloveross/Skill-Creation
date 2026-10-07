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
                     "credits": Decimal("0"), "rule": rule, "fee_entry_ids": []}

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

    # Fee entries are mapped to their withdrawal. A later credit must instead
    # identify the specific erroneous fee entry it corrected; same-day or
    # same-withdrawal proximity alone is not enough, particularly for duplicates.
    fee_to_withdrawal = {}
    for index, item in enumerate(fees):
        if not isinstance(item, dict):
            raise ValueError(f"fee_entries[{index}] must be an object")
        entry_id = require_id(item.get("entry_id"), f"fee_entries[{index}].entry_id")
        if entry_id in fee_to_withdrawal:
            raise ValueError("fee_entries entry_id values must be unique")
        wid = require_id(item.get("withdrawal_id"), f"fee_entries[{index}].withdrawal_id")
        if wid not in rows:
            raise ValueError(f"fee_entries[{index}] references an unknown withdrawal_id")
        if item.get("status") != "posted":
            raise ValueError(f"fee_entries[{index}] must be posted")
        fee_to_withdrawal[entry_id] = wid
        rows[wid]["fees"] += positive(item.get("amount"), f"fee_entries[{index}].amount")
        rows[wid]["fee_entry_ids"].append(entry_id)

    seen_credits = set()
    for index, item in enumerate(credits):
        if not isinstance(item, dict):
            raise ValueError(f"prior_corrections[{index}] must be an object")
        entry_id = require_id(item.get("entry_id"), f"prior_corrections[{index}].entry_id")
        if entry_id in seen_credits:
            raise ValueError("prior_corrections entry_id values must be unique")
        seen_credits.add(entry_id)
        fee_entry_id = require_id(item.get("fee_entry_id"), f"prior_corrections[{index}].fee_entry_id")
        if fee_entry_id not in fee_to_withdrawal:
            raise ValueError(f"prior_corrections[{index}] references an unknown fee_entry_id")
        if item.get("status") != "posted":
            raise ValueError(f"prior_corrections[{index}] must be posted")
        rows[fee_to_withdrawal[fee_entry_id]]["credits"] += positive(item.get("amount"), f"prior_corrections[{index}].amount")

    result_rows = []
    total = Decimal("0")
    for row in rows.values():
        gross_overcharge = max(row["fees"] - row["expected"], Decimal("0"))
        # Credits here are limited to credits proven to correct an excess fee entry,
        # not rebates associated with a valid scheduled fee or with an operator fee.
        correction = max(gross_overcharge - row["credits"], Decimal("0")).quantize(CENT)
        total += correction
        result_rows.append({
            "withdrawal_id": row["withdrawal_id"],
            "mapped_fee_entry_ids": row["fee_entry_ids"],
            "expected_bank_fee": money(row["expected"]),
            "posted_bank_fee_total": money(row["fees"]),
            "gross_fee_overcharge": money(gross_overcharge),
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
