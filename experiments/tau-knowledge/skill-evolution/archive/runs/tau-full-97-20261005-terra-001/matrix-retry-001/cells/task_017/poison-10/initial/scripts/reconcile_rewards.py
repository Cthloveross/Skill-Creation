#!/usr/bin/env python3
"""Calculate review-only reward expectations for Silver Rewards Card transactions.

Input: one JSON object described in SKILL.md on stdin.
Output: one JSON object. The program never contacts a service or changes records.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

POSTED_STATUSES = {"COMPLETED", "POSTED", "SETTLED"}
EXCLUDED_STATUSES = {"REFUNDED", "RETURNED", "VOIDED", "REVERSED", "CANCELLED"}
SILVER_BONUS_CATEGORIES = {"travel": Decimal("4.0"), "software": Decimal("4.0")}


def text(value):
    return str(value).strip()


def decimal_value(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(label + " must be a decimal number")
    raw = text(value).replace(",", "")
    if raw.startswith("$"):
        raw = raw[1:].strip()
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError(label + " must be a decimal number")
    if not parsed.is_finite():
        raise ValueError(label + " must be finite")
    return parsed


def parse_amount(value):
    amount = decimal_value(value, "transaction_amount")
    if amount < 0:
        raise ValueError("transaction_amount must not be negative")
    # Currency inputs may have no more than cents.
    if amount.as_tuple().exponent < -2:
        raise ValueError("transaction_amount must have no more than two decimal places")
    return amount


def parse_rate(value, label):
    rate = decimal_value(value, label)
    if rate < 0 or rate > 100:
        raise ValueError(label + " must be between 0 and 100 percent")
    return rate


def parse_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    raw = text(value).lower()
    if raw.endswith(" points"):
        raw = raw[:-7].strip()
    elif raw.endswith(" point"):
        raw = raw[:-6].strip()
    try:
        points = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    if not points.is_finite() or points < 0 or points != points.to_integral_value():
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    return int(points)


def object_of_rates(value, label, normalize_key):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    result = {}
    for key, rate in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(label + " keys must be nonempty strings")
        result[normalize_key(key)] = parse_rate(rate, label + " value for " + key)
    return result


def points_for(amount, rate_percent):
    # percent -> decimal cash-back rate -> dollars -> cents/points, floored per transaction
    raw_points = amount * rate_percent
    return int(raw_points.to_integral_value(rounding=ROUND_FLOOR))


def select_rate(card_type, txn_id, category, base_rate, category_rates, promotions):
    if txn_id in promotions:
        return promotions[txn_id], "verified_transaction_promotion"
    if category in category_rates:
        return category_rates[category], "verified_category_rate"
    if card_type == "Silver Rewards Card" and category in SILVER_BONUS_CATEGORIES:
        return SILVER_BONUS_CATEGORIES[category], "Silver_4_percent_bonus"
    if base_rate is not None:
        return base_rate, "verified_base_rate"
    return None, None


def review_transaction(txn, card_type, base_rate, category_rates, promotions):
    if not isinstance(txn, dict):
        raise ValueError("every transactions entry must be an object")
    required = ["transaction_id", "transaction_amount", "category", "status", "rewards_earned"]
    absent = [key for key in required if key not in txn]
    if absent:
        raise ValueError("transaction missing required field(s): " + ", ".join(absent))
    txn_id = text(txn["transaction_id"])
    if not txn_id:
        raise ValueError("transaction_id must be nonempty")
    amount = parse_amount(txn["transaction_amount"])
    stored = parse_points(txn["rewards_earned"])
    category = text(txn["category"]).casefold()
    status = text(txn["status"]).upper()
    if not category:
        raise ValueError("category must be nonempty for " + txn_id)
    if not status:
        raise ValueError("status must be nonempty for " + txn_id)

    result = {
        "transaction_id": txn_id,
        "posted_category": text(txn["category"]),
        "status": status,
        "stored_points": stored,
    }
    if status in EXCLUDED_STATUSES:
        result.update({"review_status": "excluded", "reason": "returned_or_reversed_transaction"})
        return result
    if status not in POSTED_STATUSES:
        result.update({"review_status": "not_final", "reason": "transaction_not_posted"})
        return result

    rate, rate_source = select_rate(card_type, txn_id, category, base_rate, category_rates, promotions)
    if rate is None:
        result.update({"review_status": "needs_rate", "reason": "no_verified_applicable_rate"})
        return result

    expected = points_for(amount, rate)
    delta = expected - stored
    result.update({
        "review_status": "calculated",
        "amount": format(amount, ".2f"),
        "applicable_rate_percent": format(rate, "f"),
        "rate_source": rate_source,
        "expected_points": expected,
        "difference_points": delta,
        "difference_cash_back": format(Decimal(delta) / Decimal("100"), ".2f"),
        "correction_candidate": delta != 0,
    })
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    card_type = text(payload.get("card_type", ""))
    if card_type != "Silver Rewards Card":
        raise ValueError("this calculator supports only card_type 'Silver Rewards Card'")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list) or not transactions:
        raise ValueError("transactions must be a nonempty array")

    base_rate = None
    if payload.get("base_rate_percent") is not None:
        base_rate = parse_rate(payload["base_rate_percent"], "base_rate_percent")
    category_rates = object_of_rates(
        payload.get("category_rates_percent"), "category_rates_percent", lambda key: key.strip().casefold()
    )
    promotions = object_of_rates(
        payload.get("promotion_rates_percent_by_transaction"),
        "promotion_rates_percent_by_transaction",
        lambda key: key.strip(),
    )

    reviews = []
    errors = []
    seen_ids = set()
    for index, transaction in enumerate(transactions):
        try:
            review = review_transaction(transaction, card_type, base_rate, category_rates, promotions)
            txn_id = review["transaction_id"]
            if txn_id in seen_ids:
                raise ValueError("duplicate transaction_id: " + txn_id)
            seen_ids.add(txn_id)
            reviews.append(review)
        except ValueError as exc:
            errors.append("transactions[" + str(index) + "]: " + str(exc))

    if errors:
        return {"ok": False, "errors": errors, "reviews": reviews}
    candidates = [item for item in reviews if item.get("correction_candidate")]
    return {"ok": True, "reviews": reviews, "candidates": candidates}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        output = main(data)
    except json.JSONDecodeError as exc:
        output = {"ok": False, "errors": ["invalid JSON: " + str(exc)]}
    except ValueError as exc:
        output = {"ok": False, "errors": [str(exc)]}
    except Exception as exc:  # Avoid partial or non-JSON output to an executor.
        output = {"ok": False, "errors": ["unexpected calculator error: " + str(exc)]}
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
