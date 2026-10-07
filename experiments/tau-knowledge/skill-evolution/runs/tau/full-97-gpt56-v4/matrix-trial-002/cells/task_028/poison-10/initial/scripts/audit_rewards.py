#!/usr/bin/env python3
"""Audit completed card-reward transactions.

Reads a JSON object from stdin. See SKILL.md for the public input/output schema.
Uses Decimal and ROUND_FLOOR so currency values and reward truncation are exact.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def decimal_value(value, field):
    """Parse a numeric value that may be formatted as a dollar/point string."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or not numeric")
    text = str(value).strip().replace(",", "").replace("$", "")
    text = text.replace("points", "").replace("point", "").strip()
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative finite number")
    return result


def as_int_points(value, field):
    parsed = decimal_value(value, field)
    if parsed != parsed.to_integral_value():
        raise ValueError(f"{field} must be a whole number of points")
    return int(parsed)


def money_string(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def record_id(transaction):
    return transaction.get("transaction_id", "<missing transaction_id>")


def audit(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions must be an array")
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        raise ValueError("card_type must be a nonempty string")
    rate = decimal_value(payload.get("earn_rate_percent"), "earn_rate_percent")
    completed_status = payload.get("completed_status", "COMPLETED")
    if not isinstance(completed_status, str) or not completed_status:
        raise ValueError("completed_status must be a nonempty string")

    categories = payload.get("eligible_categories")
    if categories is not None:
        if not isinstance(categories, list) or not all(isinstance(x, str) for x in categories):
            raise ValueError("eligible_categories must be an array of strings")
        eligible_categories = {x.casefold().strip() for x in categories}
    else:
        eligible_categories = None

    result = {
        "card_type": card_type,
        "earn_rate_percent": str(rate),
        "completed_status": completed_status,
        "matched_card_count": 0,
        "audited": [],
        "matches": [],
        "mismatches": [],
        "indeterminate": [],
        "skipped": [],
    }

    for transaction in transactions:
        if not isinstance(transaction, dict):
            result["skipped"].append({"transaction_id": "<unreadable>", "reason": "transaction is not an object"})
            continue
        if transaction.get("credit_card_type") != card_type:
            continue
        result["matched_card_count"] += 1
        txid = record_id(transaction)
        if transaction.get("status") != completed_status:
            result["skipped"].append({"transaction_id": txid, "reason": "transaction is not completed"})
            continue
        category = transaction.get("category")
        category_key = category.casefold().strip() if isinstance(category, str) else ""
        if eligible_categories is not None and category_key not in eligible_categories:
            result["indeterminate"].append({
                "transaction_id": txid,
                "category": category,
                "reason": "category is not in supplied documented eligible categories",
            })
            continue
        try:
            amount = decimal_value(transaction.get("transaction_amount"), "transaction_amount")
            awarded = as_int_points(transaction.get("rewards_earned"), "rewards_earned")
        except ValueError as exc:
            result["skipped"].append({"transaction_id": txid, "reason": str(exc)})
            continue
        expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
        difference = expected - awarded
        detail = {
            "transaction_id": txid,
            "transaction_date": transaction.get("transaction_date"),
            "merchant_name": transaction.get("merchant_name"),
            "category": category,
            "transaction_amount": money_string(amount),
            "awarded_points": awarded,
            "expected_points": expected,
            "point_difference": difference,
            "awarded_cash_value": money_string(Decimal(awarded) / Decimal(100)),
            "expected_cash_value": money_string(Decimal(expected) / Decimal(100)),
            "cash_difference": money_string(Decimal(difference) / Decimal(100)),
            "calculation": f"floor({money_string(amount)} * {rate})",
        }
        result["audited"].append(detail)
        if difference == 0:
            result["matches"].append(detail)
        else:
            result["mismatches"].append(detail)

    result["audited_count"] = len(result["audited"])
    result["match_count"] = len(result["matches"])
    result["mismatch_count"] = len(result["mismatches"])
    result["indeterminate_count"] = len(result["indeterminate"])
    result["skipped_count"] = len(result["skipped"])
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(audit(payload), ensure_ascii=False, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
