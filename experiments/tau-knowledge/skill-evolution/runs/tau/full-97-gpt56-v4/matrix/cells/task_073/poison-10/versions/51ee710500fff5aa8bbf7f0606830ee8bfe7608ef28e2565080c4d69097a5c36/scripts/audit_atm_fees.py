#!/usr/bin/env python3
"""Calculate an itemized ATM-fee review from explicitly classified transaction data.

Reads one JSON object from stdin and writes one JSON object to stdout. It does not
access bank systems or perform any account action.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ALLOWED_CLASSES = {"Blue Account", "Green Account", "Light Green Account"}
ALLOWED_ROUTES = {"domestic_in_network", "domestic_out_of_network", "foreign"}
ALLOWED_SOURCES = {"bank", "operator"}
ALLOWED_STATUSES = {"posted", "pending"}


def money(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = abs(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be MM/DD/YYYY")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise ValueError(f"{field} must be MM/DD/YYYY")


def require_string(row, key, prefix):
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}.{key} must be a nonempty string")
    return value.strip()


def expected_fee(account_class, route, withdrawal_amount, domestic_sequence):
    if route == "domestic_in_network":
        return Decimal("0.00"), None
    if account_class == "Blue Account":
        if route == "domestic_out_of_network":
            return min(withdrawal_amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP), None
        return max(withdrawal_amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP), None
    if account_class == "Green Account":
        if route == "domestic_out_of_network":
            return Decimal("3.00"), None
        return max(withdrawal_amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP), None
    # Light Green
    if route == "domestic_out_of_network":
        if domestic_sequence <= 4:
            return Decimal("0.00"), domestic_sequence
        return Decimal("1.50"), domestic_sequence
    if withdrawal_amount <= Decimal("100.00"):
        return Decimal("2.00"), None
    if withdrawal_amount <= Decimal("300.00"):
        return Decimal("3.50"), None
    return Decimal("5.00"), None


def as_money_text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account_class = payload.get("account_class")
    if account_class not in ALLOWED_CLASSES:
        raise ValueError("account_class must be Blue Account, Green Account, or Light Green Account")
    withdrawals = payload.get("withdrawals")
    fees = payload.get("fees")
    if not isinstance(withdrawals, list) or not isinstance(fees, list):
        raise ValueError("withdrawals and fees must be arrays")

    parsed_withdrawals = []
    seen_withdrawal_ids = set()
    for index, row in enumerate(withdrawals):
        if not isinstance(row, dict):
            raise ValueError(f"withdrawals[{index}] must be an object")
        wid = require_string(row, "withdrawal_id", f"withdrawals[{index}]")
        if wid in seen_withdrawal_ids:
            raise ValueError(f"duplicate withdrawal_id: {wid}")
        seen_withdrawal_ids.add(wid)
        route = row.get("route")
        status = row.get("status")
        if route not in ALLOWED_ROUTES:
            raise ValueError(f"withdrawals[{index}].route is invalid")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"withdrawals[{index}].status must be posted or pending")
        parsed_withdrawals.append({
            "withdrawal_id": wid,
            "date": parse_date(row.get("date"), f"withdrawals[{index}].date"),
            "amount": money(row.get("amount"), f"withdrawals[{index}].amount"),
            "route": route,
            "status": status,
        })

    fees_by_withdrawal = defaultdict(list)
    pending_fee_ids = []
    operator_fee_ids = []
    seen_fee_ids = set()
    for index, row in enumerate(fees):
        if not isinstance(row, dict):
            raise ValueError(f"fees[{index}] must be an object")
        fid = require_string(row, "fee_id", f"fees[{index}]")
        if fid in seen_fee_ids:
            raise ValueError(f"duplicate fee_id: {fid}")
        seen_fee_ids.add(fid)
        wid = require_string(row, "withdrawal_id", f"fees[{index}]")
        if wid not in seen_withdrawal_ids:
            raise ValueError(f"fee {fid} is paired to unknown withdrawal_id {wid}")
        source = row.get("fee_source")
        status = row.get("status")
        if source not in ALLOWED_SOURCES:
            raise ValueError(f"fees[{index}].fee_source must be bank or operator")
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"fees[{index}].status must be posted or pending")
        item = {"fee_id": fid, "amount": money(row.get("amount"), f"fees[{index}].amount"), "fee_source": source, "status": status}
        fees_by_withdrawal[wid].append(item)
        if status == "pending":
            pending_fee_ids.append(fid)
        if source == "operator":
            operator_fee_ids.append(fid)

    # Only posted domestic OON Light Green withdrawals participate in its monthly count.
    domestic_order = sorted(
        (w for w in parsed_withdrawals if w["status"] == "posted" and w["route"] == "domestic_out_of_network"),
        key=lambda w: (w["date"], w["withdrawal_id"]),
    )
    domestic_sequence = {w["withdrawal_id"]: i + 1 for i, w in enumerate(domestic_order)}

    items = []
    total = Decimal("0.00")
    pending_withdrawal_ids = []
    for w in sorted(parsed_withdrawals, key=lambda x: (x["date"], x["withdrawal_id"])):
        related = fees_by_withdrawal[w["withdrawal_id"]]
        if w["status"] != "posted":
            pending_withdrawal_ids.append(w["withdrawal_id"])
            continue
        posted_bank_fees = [f for f in related if f["status"] == "posted" and f["fee_source"] == "bank"]
        actual = sum((f["amount"] for f in posted_bank_fees), Decimal("0.00"))
        sequence = domestic_sequence.get(w["withdrawal_id"], 0)
        expected, light_count = expected_fee(account_class, w["route"], w["amount"], sequence)
        overcharge = max(actual - expected, Decimal("0.00"))
        total += overcharge
        items.append({
            "withdrawal_id": w["withdrawal_id"],
            "date": w["date"].strftime("%m/%d/%Y"),
            "withdrawal_amount": as_money_text(w["amount"]),
            "route": w["route"],
            "light_green_domestic_out_of_network_sequence": light_count,
            "expected_bank_fee": as_money_text(expected),
            "actual_posted_bank_fee": as_money_text(actual),
            "difference_actual_minus_expected": as_money_text(actual - expected),
            "positive_overcharge": as_money_text(overcharge),
            "bank_fee_ids": [f["fee_id"] for f in posted_bank_fees],
            "status": (
                "overcharged" if actual > expected
                else "correct" if actual == expected
                else "undercharged_or_missing_fee"
            ),
        })

    return {
        "account_class": account_class,
        "items": items,
        "total_overcharge": as_money_text(total),
        "pending_withdrawal_ids_excluded": pending_withdrawal_ids,
        "pending_fee_ids_excluded": pending_fee_ids,
        "operator_fee_ids_excluded": operator_fee_ids,
        "notice": "Operator fees and pending items are excluded. Output is a calculation aid, not authorization to apply a credit.",
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("expected one JSON object on stdin")
        print(json.dumps(main(json.loads(raw)), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stdout)
        sys.exit(2)
