#!/usr/bin/env python3
"""Analyze documented Crypto-Cash Back transaction accrual from JSON stdin.

Input: {"transactions": [transaction objects]}
Output: {"flagged": [...], "matching": [...], "unsupported": [...], "invalid": [...]}
No account actions are performed.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

CRYPTO_CARD = "Crypto-Cash Back"


def amount_to_decimal(value):
    if isinstance(value, bool) or value is None:
        raise InvalidOperation("missing amount")
    text = str(value).strip().replace("$", "").replace(",", "")
    amount = Decimal(text)
    if amount < 0:
        raise InvalidOperation("negative amount")
    return amount


def to_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing rewards_earned")
    points = int(str(value).strip())
    if points < 0:
        raise ValueError("negative rewards_earned")
    return points


def money(points):
    return format((Decimal(points) / Decimal(100)).quantize(Decimal("0.01")), ".2f")


def analyze_transaction(txn):
    if not isinstance(txn, dict):
        return "invalid", {"reason": "transaction must be an object", "record": txn}
    transaction_id = txn.get("transaction_id")
    card_type = txn.get("credit_card_type")
    if card_type != CRYPTO_CARD:
        return "unsupported", {
            "transaction_id": transaction_id,
            "reason": "No documented rate is available in this Skill for this card type."
        }
    if str(txn.get("status", "")).upper() != "COMPLETED":
        return "unsupported", {
            "transaction_id": transaction_id,
            "reason": "Only completed transactions are evaluated."
        }
    try:
        amount = amount_to_decimal(txn.get("transaction_amount"))
        actual = to_points(txn.get("rewards_earned"))
    except (InvalidOperation, ValueError) as exc:
        return "invalid", {"transaction_id": transaction_id, "reason": str(exc)}

    # 2.0% cash back is 2 stored points per dollar; fractional points floor.
    expected = int((amount * Decimal(2)).to_integral_value(rounding=ROUND_FLOOR))
    result = {
        "transaction_id": transaction_id,
        "merchant_name": txn.get("merchant_name"),
        "transaction_date": txn.get("transaction_date"),
        "category": txn.get("category"),
        "amount_dollars": format(amount.quantize(Decimal("0.01")), ".2f"),
        "recorded_points": actual,
        "recorded_cash_equivalent_dollars": money(actual),
        "expected_points": expected,
        "expected_cash_equivalent_dollars": money(expected),
        "difference_points": expected - actual,
        "difference_cash_equivalent_dollars": money(abs(expected - actual)),
        "calculation": "floor(amount_dollars * 2)"
    }
    return ("matching" if actual == expected else "flagged"), result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "message": str(exc)}))
        return
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "invalid_input", "message": "transactions must be an array"}))
        return
    output = {"flagged": [], "matching": [], "unsupported": [], "invalid": []}
    for txn in transactions:
        bucket, record = analyze_transaction(txn)
        output[bucket].append(record)
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
