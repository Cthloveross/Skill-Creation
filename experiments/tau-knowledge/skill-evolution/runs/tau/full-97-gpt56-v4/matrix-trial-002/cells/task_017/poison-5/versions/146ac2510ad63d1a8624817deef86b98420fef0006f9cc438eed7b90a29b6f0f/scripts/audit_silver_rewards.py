#!/usr/bin/env python3
"""Audit supplied Silver Rewards Card transaction records.

Reads a JSON object from stdin. Writes a JSON object. No network or bank actions
are performed. Monetary and point calculations use Decimal and are serialized as
strings so callers can present them without binary floating-point artifacts.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BONUS_CATEGORIES = {"travel", "software"}
POSTED_STATUSES = {"COMPLETED", "POSTED"}
POINT_VALUE = Decimal("0.01")
ROUNDING_TOLERANCE_POINTS = Decimal("1")


def decimal_value(value, field):
    """Return a nonnegative Decimal for a number/string input or raise ValueError."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a nonnegative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a nonnegative number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative number")
    return result


def fmt(value, places=None):
    """Format Decimal without exponent notation, optionally to fixed places."""
    if places is not None:
        value = value.quantize(Decimal("1").scaleb(-places))
    return format(value, "f")


def audit_transaction(txn, index):
    """Return a transaction audit, retaining only non-sensitive supplied labels."""
    if not isinstance(txn, dict):
        return {"index": index, "classification": "not_assessed",
                "reason": "Transaction record is not an object."}

    result = {"index": index}
    for field in ("transaction_id", "merchant_name", "category", "status"):
        if field in txn and txn[field] is not None:
            result[field] = str(txn[field])

    if txn.get("is_excluded") is True:
        result.update({"classification": "not_assessed",
                       "reason": "Known rewards exclusion; no eligible earnings calculation was made."})
        return result

    status = str(txn.get("status", "")).upper()
    if status not in POSTED_STATUSES:
        result.update({"classification": "not_assessed",
                       "reason": "Transaction is not marked POSTED or COMPLETED; rewards are assessed after posting."})
        return result

    try:
        amount = decimal_value(txn.get("transaction_amount"), "transaction_amount")
        earned = decimal_value(txn.get("rewards_earned"), "rewards_earned")
    except ValueError as exc:
        result.update({"classification": "not_assessed", "reason": str(exc)})
        return result

    category = str(txn.get("category", "")).strip().lower()
    bonus = category in BONUS_CATEGORIES
    rate = Decimal("0.04") if bonus else Decimal("0.01")
    expected_points = amount * rate * Decimal("100")
    earned_cash = earned * POINT_VALUE
    expected_cash = expected_points * POINT_VALUE
    # A whole-point award can reasonably be one point below or above the exact
    # decimal calculation. Values below that band are material shortfalls.
    materially_low = earned + ROUNDING_TOLERANCE_POINTS < expected_points

    result.update({
        "transaction_amount": fmt(amount, 2),
        "category_rate_kind": "bonus" if bonus else "minimum",
        "expected_rate_percent": fmt(rate * 100, 1),
        "expected_points_before_rounding": fmt(expected_points),
        "expected_cash_back_before_rounding": fmt(expected_cash, 2),
        "earned_points": fmt(earned),
        "earned_cash_back": fmt(earned_cash, 2),
        "rounding_tolerance_points": fmt(ROUNDING_TOLERANCE_POINTS),
    })
    if materially_low:
        shortfall = expected_points - earned
        result.update({
            "classification": "reviewable_under_credited",
            "apparent_shortfall_points_before_rounding": fmt(shortfall),
            "apparent_shortfall_cash_back_before_rounding": fmt(shortfall * POINT_VALUE, 2),
            "reason": ("Earned points are more than one whole point below the "
                       "documented rate calculation; seek a rewards review rather than promising an adjustment.")
        })
    elif bonus:
        result.update({
            "classification": "consistent_with_rate",
            "reason": "Earned points are within one-point rounding of the 4.0% bonus rate."})
    else:
        result.update({
            "classification": "meets_minimum",
            "reason": "Earned points meet the documented 1.0% minimum within one-point rounding."})
    return result


def main(payload):
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Input must be a JSON object."}
    if payload.get("card_type") != "Silver Rewards Card":
        return {"ok": False,
                "error": "This calculator supports only card_type 'Silver Rewards Card'."}
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        return {"ok": False, "error": "transactions must be a JSON array."}

    output = {
        "ok": True,
        "card_type": "Silver Rewards Card",
        "point_value_dollars": fmt(POINT_VALUE, 2),
        "transactions": [audit_transaction(txn, i) for i, txn in enumerate(transactions)],
    }
    if "account_reward_points" in payload and payload["account_reward_points"] is not None:
        try:
            balance = decimal_value(payload["account_reward_points"], "account_reward_points")
            output["account_reward_points"] = fmt(balance)
            output["account_reward_cash_value"] = fmt(balance * POINT_VALUE, 2)
        except ValueError as exc:
            output["account_reward_balance_note"] = str(exc)
    return output


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), separators=(",", ":")))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"Invalid JSON input: {exc.msg}"}, separators=(",", ":")))
