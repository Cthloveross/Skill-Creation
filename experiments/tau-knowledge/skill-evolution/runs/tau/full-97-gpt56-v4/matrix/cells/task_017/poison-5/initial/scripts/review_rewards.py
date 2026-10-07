#!/usr/bin/env python3
"""Review posted Silver Rewards Card 4% Travel/Software rewards.

Reads JSON from stdin and writes JSON to stdout.  Uses Decimal to avoid binary
floating-point errors.  See SKILL.md for the public input/output contract.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

SUPPORTED_CARD = "Silver Rewards Card"
BONUS_CATEGORIES = {"travel", "software"}
POINTS_PER_DOLLAR = Decimal("100")
RATE = Decimal("0.04")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s must be a decimal value" % field)
    if not result.is_finite() or result < 0:
        raise ValueError("%s must be a finite non-negative value" % field)
    return result


def integer_points(value, field):
    amount = decimal_value(value, field)
    if amount != amount.to_integral_value():
        raise ValueError("%s must be a whole number of points" % field)
    return int(amount)


def money(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def review_transaction(txn):
    required = ("transaction_amount", "category", "status", "rewards_earned")
    missing = [key for key in required if key not in txn]
    if missing:
        raise ValueError("transaction missing required field(s): " + ", ".join(missing))

    status = str(txn["status"]).upper()
    category = str(txn["category"]).strip()
    basic = {
        "transaction_id": txn.get("transaction_id"),
        "merchant_name": txn.get("merchant_name"),
        "transaction_date": txn.get("transaction_date"),
        "transaction_amount": str(txn["transaction_amount"]),
        "category": category,
        "status": status,
        "actual_points": integer_points(txn["rewards_earned"], "rewards_earned"),
    }
    if status != "COMPLETED":
        basic["exclusion_reason"] = "not_posted_or_not_completed"
        return "excluded", basic
    if category.casefold() not in BONUS_CATEGORIES:
        basic["exclusion_reason"] = "default_rate_not_established_for_category"
        return "excluded", basic

    charge = decimal_value(txn["transaction_amount"], "transaction_amount")
    actual = basic["actual_points"]
    exact_points = charge * RATE * POINTS_PER_DOLLAR
    nearest = int(exact_points.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    truncated = int(exact_points.quantize(Decimal("1"), rounding=ROUND_DOWN))
    expected_cash_exact = charge * RATE

    if actual == nearest:
        conclusion = "matches_nearest_cent"
    elif actual == truncated and truncated != nearest:
        conclusion = "rounding_dependent"
    else:
        conclusion = "confirmed_mismatch"

    basic.update({
        "documented_rate_percent": "4.0",
        "actual_cash_back_dollars": money(Decimal(actual) / POINTS_PER_DOLLAR),
        "expected_cash_back_exact_dollars": str(expected_cash_exact),
        "expected_cash_back_nearest_cent_dollars": money(expected_cash_exact),
        "expected_points_exact": str(exact_points),
        "expected_points_nearest_cent": nearest,
        "expected_points_truncated": truncated,
        "difference_from_nearest_cent_points": actual - nearest,
        "conclusion": conclusion,
    })
    return "reviewed", basic


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    if payload.get("card_type") != SUPPORTED_CARD:
        raise ValueError("only Silver Rewards Card is supported")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a JSON array")

    reviewed, excluded = [], []
    for txn in transactions:
        if not isinstance(txn, dict):
            raise ValueError("each transaction must be a JSON object")
        kind, row = review_transaction(txn)
        (reviewed if kind == "reviewed" else excluded).append(row)

    summary = {
        "input_transaction_count": len(transactions),
        "reviewed_transaction_count": len(reviewed),
        "excluded_transaction_count": len(excluded),
        "actual_points_reviewed": sum(row["actual_points"] for row in reviewed),
        "expected_points_nearest_cent_reviewed": sum(row["expected_points_nearest_cent"] for row in reviewed),
        "confirmed_mismatch_count": sum(row["conclusion"] == "confirmed_mismatch" for row in reviewed),
        "rounding_dependent_count": sum(row["conclusion"] == "rounding_dependent" for row in reviewed),
        "note": "Totals do not replace transaction-level review because rounding may occur per transaction.",
    }
    return {
        "review_scope": "completed Travel and Software transactions at the documented 4.0% Silver Rewards Card rate",
        "points_conversion": "100 points = 1.00 dollar cash back",
        "rounding_note": "Source materials do not specify integer-point rounding; nearest-cent and truncation are both shown.",
        "reviewed": reviewed,
        "excluded": excluded,
        "summary": summary,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
