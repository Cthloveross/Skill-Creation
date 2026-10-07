#!/usr/bin/env python3
"""Analyze documented Crypto-Cash Back earnings from JSON stdin; emit JSON stdout."""
import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

REQUIRED = ("transaction_id", "credit_card_type", "transaction_amount", "status", "rewards_earned")


def as_decimal(value, field, index):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"transactions[{index}].{field} must be numeric")
    if not result.is_finite() or result < 0:
        raise ValueError(f"transactions[{index}].{field} must be a nonnegative finite number")
    return result


def analyze(transaction, index):
    if not isinstance(transaction, dict):
        raise ValueError(f"transactions[{index}] must be an object")
    missing = [key for key in REQUIRED if key not in transaction]
    if missing:
        raise ValueError(f"transactions[{index}] missing: {', '.join(missing)}")
    amount = as_decimal(transaction["transaction_amount"], "transaction_amount", index)
    recorded = as_decimal(transaction["rewards_earned"], "rewards_earned", index)
    if recorded != recorded.to_integral_value():
        raise ValueError(f"transactions[{index}].rewards_earned must be whole points")
    eligibility = transaction.get("eligibility", "unknown")
    if eligibility not in ("eligible", "ineligible", "unknown"):
        raise ValueError(f"transactions[{index}].eligibility must be eligible, ineligible, or unknown")
    result = {
        "transaction_id": str(transaction["transaction_id"]),
        "card_type": transaction["credit_card_type"],
        "recorded_points": int(recorded),
        "recorded_cash_back_dollars": format(recorded / Decimal("100"), ".2f"),
        "comparable": False,
        "reason": None,
    }
    if transaction["credit_card_type"] != "Crypto-Cash Back":
        result["reason"] = "No documented earning rate is available to this analyzer for this card type."
    elif str(transaction["status"]).upper() != "COMPLETED":
        result["reason"] = "Transaction is not completed."
    elif eligibility == "ineligible":
        result["reason"] = "Transaction is explicitly ineligible."
    elif eligibility == "unknown":
        result["reason"] = "Eligibility is unknown; no conclusive comparison was made."
    else:
        expected = int((amount * Decimal("2")).to_integral_value(rounding=ROUND_FLOOR))
        result.update({
            "comparable": True,
            "expected_points": expected,
            "expected_cash_back_dollars": format(Decimal(expected) / Decimal("100"), ".2f"),
            "point_difference": expected - int(recorded),
            "apparent_discrepancy": expected != int(recorded),
            "calculation": "floor(transaction_amount * 2)",
        })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        analyses = [analyze(item, i) for i, item in enumerate(payload["transactions"])]
        comparable = [item for item in analyses if item["comparable"]]
        output = {
            "analyses": analyses,
            "summary": {
                "transactions_received": len(analyses),
                "comparable_transactions": len(comparable),
                "apparent_discrepancies": sum(1 for item in comparable if item["apparent_discrepancy"]),
            },
        }
        print(json.dumps(output, separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
