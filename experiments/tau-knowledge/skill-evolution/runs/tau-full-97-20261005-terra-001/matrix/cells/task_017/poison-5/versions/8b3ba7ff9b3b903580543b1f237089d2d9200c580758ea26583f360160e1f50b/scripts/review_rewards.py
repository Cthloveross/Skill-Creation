#!/usr/bin/env python3
"""Calculate review-only rewards comparisons from JSON stdin to JSON stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP

ROUNDING = {
    "floor": ROUND_FLOOR,
    "half_up": ROUND_HALF_UP,
    "half_even": ROUND_HALF_EVEN,
    "ceil": ROUND_CEILING,
}


def decimal_value(value, field):
    try:
        result = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field} must be a decimal value")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def points_value(value):
    """Accept a numeric value or common storage display such as '400 points'."""
    text = str(value).strip().lower()
    if text.endswith("points"):
        text = text[:-6].strip()
    elif text.endswith("point"):
        text = text[:-5].strip()
    return decimal_value(text, "rewards_earned")


def fmt(value):
    """Return a stable non-exponent decimal string."""
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result or "0"


def completed(status):
    return str(status).strip().upper() in {"COMPLETED", "POSTED"}


def review_transaction(txn, rates, default_rate, point_value, rounding_mode):
    required = ["transaction_id", "merchant_name", "transaction_amount", "category", "status", "rewards_earned"]
    missing = [key for key in required if key not in txn]
    if missing:
        return {"transaction_id": txn.get("transaction_id"), "outcome": "invalid_transaction", "error": "missing fields: " + ", ".join(missing)}

    base = {
        "transaction_id": str(txn["transaction_id"]),
        "merchant_name": str(txn["merchant_name"]),
        "category": str(txn["category"]),
        "status": str(txn["status"]),
    }
    try:
        amount = decimal_value(txn["transaction_amount"], "transaction_amount")
        observed = points_value(txn["rewards_earned"])
    except ValueError as exc:
        base.update({"outcome": "invalid_transaction", "error": str(exc)})
        return base
    if amount < 0 or observed < 0:
        base.update({"outcome": "invalid_transaction", "error": "amount and rewards_earned cannot be negative"})
        return base

    base.update({"amount": fmt(amount), "recorded_points": fmt(observed), "recorded_cash_value": fmt(observed * point_value)})
    if bool(txn.get("refunded", False)):
        base["outcome"] = "not_eligible_or_not_posted"
        base["reason"] = "transaction is refunded or credited; rewards may be reversed"
        return base
    if not completed(txn["status"]):
        base["outcome"] = "not_eligible_or_not_posted"
        base["reason"] = "transaction is not posted or completed"
        return base

    category = str(txn["category"])
    rate = rates.get(category, default_rate)
    if rate is None:
        base["outcome"] = "rate_not_documented"
        base["reason"] = "no verified rate was supplied for this category"
        return base

    expected_exact = amount * rate / point_value
    base.update({"rate": fmt(rate), "expected_points_exact": fmt(expected_exact), "expected_cash_value": fmt(amount * rate)})
    if rounding_mode is None and expected_exact != expected_exact.to_integral_value():
        base["outcome"] = "rounding_policy_needed"
        base["reason"] = "exact expected points are fractional and no authoritative rounding mode was supplied"
        return base

    expected_whole = expected_exact if rounding_mode is None else expected_exact.quantize(Decimal("1"), rounding=ROUNDING[rounding_mode])
    base["expected_points_whole"] = fmt(expected_whole)
    base["difference_points"] = fmt(expected_whole - observed)
    base["outcome"] = "matches_documented_calculation" if observed == expected_whole else "discrepancy_identified"
    return base


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    transactions = payload.get("transactions")
    rates_raw = payload.get("rates_by_category")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    if not isinstance(rates_raw, dict):
        raise ValueError("rates_by_category must be an object")

    point_value = decimal_value(payload.get("point_value", "0.01"), "point_value")
    if point_value <= 0:
        raise ValueError("point_value must be greater than zero")
    rates = {}
    for category, rate in rates_raw.items():
        parsed = decimal_value(rate, f"rate for {category}")
        if parsed < 0:
            raise ValueError(f"rate for {category} cannot be negative")
        rates[str(category)] = parsed
    default_rate = None
    if "default_rate" in payload and payload["default_rate"] is not None:
        default_rate = decimal_value(payload["default_rate"], "default_rate")
        if default_rate < 0:
            raise ValueError("default_rate cannot be negative")
    rounding_mode = payload.get("rounding_mode")
    if rounding_mode is not None and rounding_mode not in ROUNDING:
        raise ValueError("rounding_mode must be one of: floor, half_up, half_even, ceil")

    results = []
    for txn in transactions:
        if not isinstance(txn, dict):
            results.append({"transaction_id": None, "outcome": "invalid_transaction", "error": "transaction must be an object"})
        else:
            results.append(review_transaction(txn, rates, default_rate, point_value, rounding_mode))
    return {"ok": True, "point_value": fmt(point_value), "rounding_mode": rounding_mode, "results": results}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))
