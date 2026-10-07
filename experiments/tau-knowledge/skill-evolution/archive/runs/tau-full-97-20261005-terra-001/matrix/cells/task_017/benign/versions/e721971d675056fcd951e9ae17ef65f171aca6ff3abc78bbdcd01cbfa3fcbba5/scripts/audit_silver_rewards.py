#!/usr/bin/env python3
"""Audit posted Silver Rewards Card cash-back points from JSON stdin.

Input schema:
{
  "card_type": "Silver Rewards Card",
  "posted_statuses": ["COMPLETED"],
  "transactions": [
    {
      "transaction_id": "...",
      "transaction_amount": "$12.34",
      "category": "Travel",
      "status": "COMPLETED",
      "rewards_earned": "49 points",
      "credit_card_type": "Silver Rewards Card"
    }
  ]
}

Output schema:
{
  "ok": true,
  "assessments": [{"state": "assessed" | "...", ...}],
  "summary": {"assessed_count": 0, "mismatch_count": 0}
}

The program performs no I/O other than stdin/stdout and makes no bank changes.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

SUPPORTED_CARD = "Silver Rewards Card"
BONUS_CATEGORIES = {"travel", "software"}
NON_POSITIVE_STATUS_MARKERS = {"REFUND", "REFUNDED", "RETURN", "RETURNED", "REVERSED", "REVERSAL", "VOID"}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def normalize(value):
    return text(value).casefold()


def parse_amount(value):
    """Parse a nonnegative monetary amount without binary floating point."""
    if isinstance(value, bool) or value is None:
        raise ValueError("transaction_amount must be a number or currency string")
    raw = str(value).strip().replace(",", "")
    if raw.startswith("$"):
        raw = raw[1:].strip()
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("transaction_amount is not a valid decimal amount")
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be finite and nonnegative")
    return amount


def parse_points(value):
    """Parse an integral, nonnegative stored-points value or return None when absent."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be a whole-point value")
    raw = str(value).strip().casefold()
    match = re.fullmatch(r"([+-]?\d+(?:\.0+)?)\s*(?:points?)?", raw)
    if not match:
        raise ValueError("rewards_earned must contain a whole number of points")
    try:
        points = Decimal(match.group(1))
    except InvalidOperation:
        raise ValueError("rewards_earned is not valid")
    if not points.is_finite() or points < 0 or points != points.to_integral_value():
        raise ValueError("rewards_earned must be nonnegative whole points")
    return int(points)


def money_from_points(points):
    return format((Decimal(points) / Decimal(100)).quantize(Decimal("0.01")), ".2f")


def invalid_assessment(transaction, message):
    return {
        "transaction_id": transaction.get("transaction_id"),
        "state": "invalid_input",
        "message": message,
    }


def assess(transaction, card_type, posted_statuses):
    if not isinstance(transaction, dict):
        return {"transaction_id": None, "state": "invalid_input", "message": "transaction must be an object"}

    transaction_id = transaction.get("transaction_id")
    if not text(transaction_id):
        return invalid_assessment(transaction, "transaction_id is required")

    transaction_card = transaction.get("credit_card_type")
    if text(transaction_card) and text(transaction_card) != card_type:
        return {
            "transaction_id": transaction_id,
            "state": "invalid_input",
            "message": "transaction credit_card_type does not match card_type",
        }
    if card_type != SUPPORTED_CARD:
        return {
            "transaction_id": transaction_id,
            "state": "unsupported_card",
            "message": "This calculator only has documented rules for Silver Rewards Card.",
        }

    status = text(transaction.get("status"))
    normalized_status = normalize(status)
    if any(marker.casefold() in normalized_status for marker in NON_POSITIVE_STATUS_MARKERS):
        return {
            "transaction_id": transaction_id,
            "state": "not_eligible_for_positive_rewards",
            "status": status,
            "message": "Returned, refunded, reversed, or voided transactions must not receive a positive reward calculation.",
        }
    if status not in posted_statuses:
        return {
            "transaction_id": transaction_id,
            "state": "needs_posting_confirmation",
            "status": status,
            "message": "The supplied status was not confirmed as posted/final.",
        }

    category = text(transaction.get("category"))
    if not category:
        return {
            "transaction_id": transaction_id,
            "state": "needs_category_confirmation",
            "status": status,
            "message": "A merchant-submitted category is required to determine the rate.",
        }

    try:
        amount = parse_amount(transaction.get("transaction_amount"))
        recorded = parse_points(transaction.get("rewards_earned"))
    except ValueError as exc:
        return invalid_assessment(transaction, str(exc))

    points_per_dollar = Decimal("4") if normalize(category) in BONUS_CATEGORIES else Decimal("1")
    expected = int((amount * points_per_dollar).to_integral_value(rounding=ROUND_FLOOR))
    result = {
        "transaction_id": transaction_id,
        "state": "assessed",
        "status": status,
        "category": category,
        "rate_points_per_dollar": str(points_per_dollar),
        "expected_points": expected,
        "expected_cash_back": "$" + money_from_points(expected),
        "recorded_points": recorded,
        "recorded_cash_back": None if recorded is None else "$" + money_from_points(recorded),
        "difference_points": None if recorded is None else expected - recorded,
        "difference_cash_back": None if recorded is None else "$" + money_from_points(abs(expected - recorded)),
        "update_payload": {"new_rewards_earned": f"{expected} points"},
    }
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": "Input must be valid JSON", "detail": str(exc)}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "error": "Input must be a JSON object"}))
        return

    card_type = text(payload.get("card_type"))
    raw_statuses = payload.get("posted_statuses")
    transactions = payload.get("transactions")
    if not card_type:
        print(json.dumps({"ok": False, "error": "card_type is required"}))
        return
    if not isinstance(raw_statuses, list) or not raw_statuses or not all(text(v) for v in raw_statuses):
        print(json.dumps({"ok": False, "error": "posted_statuses must be a nonempty list of confirmed status strings"}))
        return
    if not isinstance(transactions, list):
        print(json.dumps({"ok": False, "error": "transactions must be a list"}))
        return

    posted_statuses = {text(v) for v in raw_statuses}
    assessments = [assess(item, card_type, posted_statuses) for item in transactions]
    assessed = [item for item in assessments if item.get("state") == "assessed"]
    mismatches = [item for item in assessed if item.get("difference_points") not in (None, 0)]
    output = {
        "ok": True,
        "card_type": card_type,
        "point_representation": "1 point = $0.01 cash back",
        "rounding": "floor to whole points",
        "assessments": assessments,
        "summary": {
            "transaction_count": len(transactions),
            "assessed_count": len(assessed),
            "mismatch_count": len(mismatches),
            "unassessed_count": len(assessments) - len(assessed),
        },
    }
    print(json.dumps(output, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
