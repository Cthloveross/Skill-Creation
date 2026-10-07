#!/usr/bin/env python3
"""Review supplied transaction records under the Crypto-Cash Back 2% rule.

Reads one JSON object from stdin with a ``transactions`` array and writes one
JSON result to stdout. No network or account actions are performed.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

SUPPORTED_CATEGORIES = {
    "Travel", "Software", "Media", "Green", "Sustainable", "Operations",
    "Transportation", "Groceries", "Dining", "Entertainment", "Utilities",
    "Shopping",
}


def parse_decimal(value, field):
    """Parse a formatted nonnegative monetary/points value exactly."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or invalid")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        text = re.sub(r"^\$", "", text)
        text = re.sub(r"\s*(?:points?|pts?)\s*$", "", text, flags=re.I)
    else:
        raise ValueError(f"{field} is missing or invalid")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative finite number")
    return result


def compact_source(txn):
    """Keep only safe context useful to the caller's explanation."""
    keys = ("transaction_id", "merchant_name", "transaction_date", "transaction_amount",
            "category", "status", "credit_card_type", "rewards_earned")
    return {key: txn[key] for key in keys if key in txn}


def review_transaction(txn):
    if not isinstance(txn, dict):
        return "error", {"reason": "transaction record must be an object"}
    source = compact_source(txn)
    if txn.get("credit_card_type") != "Crypto-Cash Back":
        return "ignored", source
    transaction_id = txn.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id.strip():
        return "manual", {**source, "reason": "missing transaction_id"}
    if txn.get("status") != "COMPLETED":
        return "manual", {**source, "reason": "transaction is not a completed purchase"}
    category = txn.get("category")
    if category not in SUPPORTED_CATEGORIES:
        return "manual", {**source, "reason": "category is not established as an eligible rewards category"}
    try:
        amount = parse_decimal(txn.get("transaction_amount"), "transaction_amount")
        recorded_decimal = parse_decimal(txn.get("rewards_earned"), "rewards_earned")
    except ValueError as exc:
        return "manual", {**source, "reason": str(exc)}
    if recorded_decimal != recorded_decimal.to_integral_value():
        return "manual", {**source, "reason": "recorded rewards are not whole points"}
    expected = (amount * Decimal("2")).to_integral_value(rounding=ROUND_FLOOR)
    result = {
        **source,
        "transaction_id": transaction_id,
        "amount_dollars": format(amount, "f"),
        "recorded_points": int(recorded_decimal),
        "expected_points": int(expected),
        "calculation": "floor(transaction_amount_dollars * 2)",
    }
    return ("match" if int(recorded_decimal) == int(expected) else "mismatch"), result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid input JSON: {exc.msg}"}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"error": "input must be an object containing a transactions array"}))
        return
    output = {"mismatches": [], "matches": [], "needs_manual_review": [],
              "ignored_non_crypto": [], "errors": []}
    for txn in payload["transactions"]:
        kind, result = review_transaction(txn)
        destination = {
            "mismatch": "mismatches", "match": "matches", "manual": "needs_manual_review",
            "ignored": "ignored_non_crypto", "error": "errors",
        }[kind]
        output[destination].append(result)
    output["summary"] = {
        "mismatch_count": len(output["mismatches"]),
        "match_count": len(output["matches"]),
        "manual_review_count": len(output["needs_manual_review"]),
        "ignored_non_crypto_count": len(output["ignored_non_crypto"]),
        "error_count": len(output["errors"]),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
