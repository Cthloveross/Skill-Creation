#!/usr/bin/env python3
"""Audit structured Gold Rewards Card and EcoCard rewards.

Reads a JSON object from stdin and emits JSON. This script never performs bank
operations; its output is a review aid, not an instruction to update rewards.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP

POINT_RE = re.compile(r"^\s*(-?\d+)\s*(?:points?)?\s*$", re.IGNORECASE)
ROUNDING = {
    "floor": ROUND_DOWN,  # reward values in this scope are non-negative
    "nearest": ROUND_HALF_UP,
    "ceiling": ROUND_CEILING,
}


def decimal_amount(value):
    if isinstance(value, bool):
        raise ValueError("amount must be a decimal number, not boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    amount = Decimal(text)
    if amount < 0:
        raise ValueError("amount must be non-negative; represent reversals with status")
    return amount


def recorded_points(value):
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = POINT_RE.match(str(value))
    if not match:
        raise ValueError("rewards_earned must be an integer or '<integer> points'")
    return int(match.group(1))


def audit_one(tx, rounding):
    required = ("transaction_id", "card_type", "amount")
    missing = [key for key in required if key not in tx or tx[key] in (None, "")]
    if missing:
        return {"transaction_id": tx.get("transaction_id"), "status": "invalid_input", "error": "missing: " + ", ".join(missing)}
    try:
        amount = decimal_amount(tx["amount"])
        observed = recorded_points(tx.get("rewards_earned"))
    except (InvalidOperation, ValueError) as exc:
        return {"transaction_id": tx.get("transaction_id"), "status": "invalid_input", "error": str(exc)}

    card = str(tx["card_type"]).strip()
    result = {
        "transaction_id": tx["transaction_id"],
        "card_type": card,
        "amount": format(amount, "f"),
        "transaction_status": tx.get("status"),
        "recorded_points": observed,
    }
    if card == "Gold Rewards Card":
        rate = Decimal("2.5")
        basis = "Gold Rewards Card: 2.5 points per dollar (2.5% cash back)"
    elif card == "EcoCard":
        eligible = tx.get("eco_green_eligible")
        if not isinstance(eligible, bool):
            result.update({
                "status": "needs_eligibility_review",
                "reason": "EcoCard green eligibility must be established from supported merchant/receipt evidence; it was not supplied.",
            })
            return result
        rate = Decimal("5") if eligible else Decimal("1")
        basis = "EcoCard: {} points per dollar based on supplied eligibility".format(rate)
    else:
        result.update({"status": "unsupported_card", "reason": "Only Gold Rewards Card and EcoCard are covered."})
        return result

    exact = amount * rate
    result["rate_points_per_dollar"] = format(rate, "f")
    result["calculation_basis"] = basis
    result["expected_exact_points"] = format(exact, "f")
    if rounding == "unresolved":
        result.update({
            "status": "needs_rounding_confirmation",
            "reason": "A whole-point rounding convention was not supplied; do not propose an automated correction.",
        })
        return result

    expected = int(exact.quantize(Decimal("1"), rounding=ROUNDING[rounding]))
    result["rounding"] = rounding
    result["expected_whole_points"] = expected
    if observed is None:
        result["status"] = "calculated_no_recorded_value"
    elif observed == expected:
        result["status"] = "matches_calculation"
    else:
        result["status"] = "discrepancy_for_review"
        result["difference_points"] = expected - observed
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        rounding = payload.get("rounding", "unresolved")
        if rounding not in ("unresolved", *ROUNDING):
            raise ValueError("rounding must be unresolved, floor, nearest, or ceiling")
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")
        results = [audit_one(tx, rounding) if isinstance(tx, dict) else {
            "status": "invalid_input", "error": "each transaction must be an object"
        } for tx in transactions]
        print(json.dumps({"rounding": rounding, "results": results}, ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
