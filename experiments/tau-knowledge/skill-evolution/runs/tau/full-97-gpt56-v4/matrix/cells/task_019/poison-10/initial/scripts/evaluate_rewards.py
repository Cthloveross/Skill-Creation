#!/usr/bin/env python3
"""Evaluate baseline credit-card rewards from JSON stdin and emit JSON stdout.

This is a calculation helper only. It performs no banking action and does not
establish merchant eligibility, customer identity, or authority.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

GOLD = "Gold Rewards Card"
ECO = "EcoCard"
VALID_QUALIFICATIONS = {"qualifying_green", "non_green", "unknown", "not_applicable"}


def parse_decimal(value):
    if isinstance(value, bool):
        raise ValueError("amount must be a decimal number, not boolean")
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("amount is not a valid decimal")
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be a non-negative finite decimal")
    return amount


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be a whole number")
    try:
        points = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("rewards_earned is not numeric")
    if not points.is_finite() or points < 0 or points != points.to_integral_value():
        raise ValueError("rewards_earned must be a non-negative whole number")
    return int(points)


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def evaluate(txn):
    transaction_id = str(txn.get("transaction_id", "")).strip()
    if not transaction_id:
        raise ValueError("transaction_id is required")
    card_type = str(txn.get("card_type", "")).strip()
    if not card_type:
        raise ValueError("card_type is required")
    amount = parse_decimal(txn.get("amount"))
    awarded = parse_points(txn.get("rewards_earned"))
    qualification = str(txn.get("qualification", "not_applicable")).strip().lower()
    if qualification not in VALID_QUALIFICATIONS:
        raise ValueError("qualification must be qualifying_green, non_green, unknown, or not_applicable")

    result = {
        "transaction_id": transaction_id,
        "card_type": card_type,
        "amount": format(amount, "f"),
        "awarded_points": awarded,
        "status": "needs_review",
        "reason": None,
        "expected_points": None,
        "difference_points": None,
    }

    if card_type == GOLD:
        expected = floor_points(amount, Decimal("2.5"))
        result.update({
            "status": "comparable",
            "reason": "Gold Rewards Card baseline is 2.5 points per dollar (2.5% cash back represented as points).",
            "expected_points": expected,
            "difference_points": expected - awarded,
        })
    elif card_type == ECO:
        if qualification == "qualifying_green":
            rate = Decimal("5")
            qualifier = "qualifying green purchase"
        elif qualification == "non_green":
            rate = Decimal("1")
            qualifier = "non-green purchase"
        else:
            result["reason"] = "EcoCard merchant/category qualification is not established; do not assume the higher rate."
            return result
        expected = floor_points(amount, rate)
        result.update({
            "status": "comparable",
            "reason": "EcoCard baseline for %s is %s points per dollar." % (qualifier, rate),
            "expected_points": expected,
            "difference_points": expected - awarded,
        })
    else:
        result["reason"] = "No supported baseline rule is packaged for this card type."
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"results": [], "errors": [{"index": None, "error": "invalid JSON: %s" % exc.msg}]}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"results": [], "errors": [{"index": None, "error": "input must be an object containing a transactions array"}]}))
        return

    results, errors = [], []
    for index, txn in enumerate(payload["transactions"]):
        if not isinstance(txn, dict):
            errors.append({"index": index, "error": "transaction must be an object"})
            continue
        try:
            results.append(evaluate(txn))
        except ValueError as exc:
            errors.append({"index": index, "transaction_id": txn.get("transaction_id"), "error": str(exc)})
    print(json.dumps({"results": results, "errors": errors}, separators=(",", ":")))


if __name__ == "__main__":
    main()
