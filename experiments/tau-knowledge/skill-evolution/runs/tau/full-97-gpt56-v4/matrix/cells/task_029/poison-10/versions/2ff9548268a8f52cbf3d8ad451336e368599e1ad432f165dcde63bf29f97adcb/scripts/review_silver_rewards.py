#!/usr/bin/env python3
"""Review completed Silver Rewards Card transactions from JSON stdin.

Input: {"transactions": [transaction, ...]}
Output: {"reviews": [...], "apparent_shortfalls": [...], "skipped": [...],
         "data_errors": [...]}
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

SILVER_CARD = "silver rewards card"
BONUS_CATEGORIES = {"travel", "software"}


def money_to_decimal(value):
    """Parse a numeric or conventional dollar string without float conversion."""
    if isinstance(value, bool):
        raise ValueError("transaction_amount must not be boolean")
    if isinstance(value, (int, Decimal)):
        amount = Decimal(value)
    elif isinstance(value, float):
        # JSON float has already lost its textual form; str is the least surprising input.
        amount = Decimal(str(value))
    elif isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        if not cleaned:
            raise ValueError("transaction_amount is empty")
        amount = Decimal(cleaned)
    else:
        raise ValueError("transaction_amount must be a number or dollar string")
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a finite nonnegative amount")
    return amount


def points_to_int(value):
    """Accept only a whole, nonnegative recorded point amount."""
    if isinstance(value, bool):
        raise ValueError("rewards_earned must not be boolean")
    try:
        points = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("rewards_earned must be a whole number")
    if not points.is_finite() or points < 0 or points != points.to_integral_value():
        raise ValueError("rewards_earned must be a nonnegative whole number")
    return int(points)


def expected_points(amount, rate_percent):
    """Floor points per purchase: dollars * rate% * 100 cents per dollar."""
    raw = amount * Decimal(str(rate_percent))
    return int(raw.to_integral_value(rounding=ROUND_FLOOR))


def text_field(record, key):
    value = record.get(key)
    return value.strip() if isinstance(value, str) else ""


def review_transaction(record, index):
    if not isinstance(record, dict):
        return None, {"index": index, "error": "transaction must be an object"}, None

    card_type = text_field(record, "credit_card_type")
    status = text_field(record, "status")
    transaction_id = text_field(record, "transaction_id")

    if card_type.casefold() != SILVER_CARD:
        return None, None, {"index": index, "transaction_id": transaction_id or None,
                            "reason": "not a Silver Rewards Card transaction"}
    if status.casefold() != "completed":
        return None, None, {"index": index, "transaction_id": transaction_id or None,
                            "reason": "transaction status is not COMPLETED"}
    if not transaction_id:
        return None, {"index": index, "error": "missing transaction_id"}, None

    try:
        amount = money_to_decimal(record.get("transaction_amount"))
        recorded = points_to_int(record.get("rewards_earned"))
    except ValueError as exc:
        return None, {"index": index, "transaction_id": transaction_id, "error": str(exc)}, None

    category = text_field(record, "category")
    is_bonus = category.casefold() in BONUS_CATEGORIES
    rate_percent = 4 if is_bonus else 1
    minimum = expected_points(amount, rate_percent)
    result = {
        "transaction_id": transaction_id,
        "merchant_name": text_field(record, "merchant_name") or None,
        "transaction_date": text_field(record, "transaction_date") or None,
        "category": category or None,
        "amount": format(amount, "f"),
        "rate_percent": rate_percent,
        "rate_basis": "documented 4% category rate" if is_bonus else "documented 1% minimum non-category rate",
        "recorded_points": recorded,
        "expected_min_points": minimum,
        "points_difference": minimum - recorded,
        "calculation": "floor(amount_dollars * %d)" % rate_percent,
        "apparent_shortfall": recorded < minimum,
    }
    return result, None, None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"reviews": [], "apparent_shortfalls": [], "skipped": [],
                          "data_errors": [{"error": "invalid JSON: " + str(exc)}]}))
        return

    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"reviews": [], "apparent_shortfalls": [], "skipped": [],
                          "data_errors": [{"error": "input must be an object with a transactions array"}]}))
        return

    reviews, shortfalls, skipped, errors = [], [], [], []
    for index, transaction in enumerate(transactions):
        review, error, skip = review_transaction(transaction, index)
        if review is not None:
            reviews.append(review)
            if review["apparent_shortfall"]:
                shortfalls.append(review)
        elif error is not None:
            errors.append(error)
        elif skip is not None:
            skipped.append(skip)

    print(json.dumps({
        "reviews": reviews,
        "apparent_shortfalls": shortfalls,
        "skipped": skipped,
        "data_errors": errors,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
