#!/usr/bin/env python3
"""Calculate review findings for cash-back transaction records.

Input: JSON object with rate_rules (category -> percent) and transactions.
Output: JSON object with records, totals, and invalid-input diagnostics.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_decimal(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} is not a valid decimal")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"status": "invalid_input", "errors": ["input must be an object"]}

    raw_rules = payload.get("rate_rules")
    raw_transactions = payload.get("transactions")
    if not isinstance(raw_rules, dict):
        errors.append("rate_rules must be an object")
        raw_rules = {}
    if not isinstance(raw_transactions, list):
        errors.append("transactions must be an array")
        raw_transactions = []

    rules = {}
    for category, raw_rate in raw_rules.items():
        if not isinstance(category, str) or not category.strip():
            errors.append("each rate rule category must be a nonempty string")
            continue
        rate = parse_decimal(raw_rate, f"rate_rules[{category!r}]", errors)
        if rate is not None and rate >= 0:
            rules[category.strip().casefold()] = rate
        elif rate is not None:
            errors.append(f"rate_rules[{category!r}] cannot be negative")

    records = []
    calculated_count = 0
    unavailable_count = 0
    potential_shortfall_count = 0
    expected_total = 0
    earned_total = 0

    for index, txn in enumerate(raw_transactions):
        item_errors = []
        if not isinstance(txn, dict):
            records.append({"index": index, "review_status": "invalid_input", "errors": ["transaction must be an object"]})
            continue

        amount = parse_decimal(txn.get("transaction_amount"), f"transactions[{index}].transaction_amount", item_errors)
        earned_raw = txn.get("rewards_earned")
        earned_decimal = parse_decimal(earned_raw, f"transactions[{index}].rewards_earned", item_errors)
        category = txn.get("category")
        status = txn.get("status")
        if amount is not None and amount < 0:
            item_errors.append("transaction_amount cannot be negative")
        if earned_decimal is not None and (earned_decimal < 0 or earned_decimal != earned_decimal.to_integral_value()):
            item_errors.append("rewards_earned must be a nonnegative whole number of points")
        if not isinstance(category, str) or not category.strip():
            item_errors.append("category must be a nonempty string")
        if not isinstance(status, str) or not status.strip():
            item_errors.append("status must be a nonempty string")

        record = {
            "index": index,
            "transaction_id": txn.get("transaction_id"),
            "merchant_name": txn.get("merchant_name"),
            "category": category,
            "status": status,
        }
        if item_errors:
            record["review_status"] = "invalid_input"
            record["errors"] = item_errors
            records.append(record)
            continue

        record["transaction_amount"] = money(amount)
        record["earned_points"] = int(earned_decimal)
        record["earned_cash_back"] = money(earned_decimal * CENT)

        # Only completed/posted records can support a final rewards comparison.
        if status.strip().upper() not in {"COMPLETED", "POSTED"}:
            record["review_status"] = "not_posted_or_completed"
            records.append(record)
            continue

        rate = rules.get(category.strip().casefold())
        if rate is None:
            record["review_status"] = "rate_unavailable"
            record["note"] = "No supplied documented rate applies to this category."
            unavailable_count += 1
            records.append(record)
            continue

        expected_points_decimal = (amount * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        expected_points = int(expected_points_decimal)
        shortfall = max(0, expected_points - int(earned_decimal))
        record.update({
            "applied_rate_percent": str(rate),
            "expected_points": expected_points,
            "expected_cash_back": money(expected_points_decimal * CENT),
            "point_difference_expected_minus_earned": expected_points - int(earned_decimal),
            "potential_shortfall_points": shortfall,
            "potential_shortfall_cash_back": money(Decimal(shortfall) * CENT),
            "review_status": "potential_shortfall" if shortfall else "meets_or_exceeds_documented_rate",
        })
        calculated_count += 1
        expected_total += expected_points
        earned_total += int(earned_decimal)
        if shortfall:
            potential_shortfall_count += 1
        records.append(record)

    return {
        "status": "invalid_input" if errors else "ok",
        "errors": errors,
        "records": records,
        "summary": {
            "input_transaction_count": len(raw_transactions),
            "calculated_transaction_count": calculated_count,
            "rate_unavailable_transaction_count": unavailable_count,
            "potential_shortfall_transaction_count": potential_shortfall_count,
            "calculated_expected_points_total": expected_total,
            "calculated_expected_cash_back_total": money(Decimal(expected_total) * CENT),
            "calculated_earned_points_total": earned_total,
            "calculated_earned_cash_back_total": money(Decimal(earned_total) * CENT),
            "calculated_potential_shortfall_points_total": max(0, expected_total - earned_total),
            "calculated_potential_shortfall_cash_back_total": money(Decimal(max(0, expected_total - earned_total)) * CENT),
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "invalid_input", "errors": [f"invalid JSON: {exc.msg}"]}, separators=(",", ":")))
