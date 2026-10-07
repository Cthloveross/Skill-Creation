#!/usr/bin/env python3
"""Audit normalized credit-card reward records from JSON stdin and emit JSON."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED_GREEN_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
GREEN_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def points(amount, multiplier):
    return int((amount * Decimal(str(multiplier))).to_integral_value(rounding=ROUND_FLOOR))


def lower(value):
    return str(value or "").strip().lower()


def audit(txn):
    required = ["transaction_id", "credit_card_type", "transaction_amount", "category", "status", "rewards_earned"]
    absent = [key for key in required if key not in txn]
    base = {"transaction_id": txn.get("transaction_id"), "card_type": txn.get("credit_card_type")}
    if absent:
        return {**base, "status": "invalid_input", "missing_fields": absent, "expected_points": None}
    try:
        amount = Decimal(str(txn["transaction_amount"]).replace("$", "").replace(",", ""))
        actual = int(txn["rewards_earned"])
        if amount < 0 or actual < 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        return {**base, "status": "invalid_input", "expected_points": None, "note": "Amount must be nonnegative decimal and rewards_earned a nonnegative integer."}

    if str(txn["status"]).upper() != "COMPLETED":
        return {**base, "status": "out_of_scope", "expected_points": None, "note": "Only completed/posted purchase transactions can be audited."}

    card, category, merchant = lower(txn["credit_card_type"]), lower(txn["category"]), lower(txn.get("merchant_name"))
    expected = None
    review_status = None
    note = None

    if card == "silver rewards card":
        expected = points(amount, 4 if category in {"travel", "software"} else 1)
    elif card == "crypto-cash back":
        # The transaction feed normally cannot prove item-level excluded activity.
        if category in {"gift card", "cash equivalent", "person-to-person", "fee", "interest", "insurance", "refund", "return"}:
            review_status, note = "needs_eligibility_review", "This category may be excluded from Crypto-Cash Back eligibility."
        else:
            expected = points(amount, 2)
    elif card == "ecocard":
        if merchant in EXCLUDED_GREEN_MERCHANTS:
            expected = points(amount, 1)
        elif "charging" in merchant and merchant not in GREEN_EV_PARTNERS:
            expected = points(amount, 1)
        elif category == "green" or merchant in GREEN_EV_PARTNERS:
            expected = points(amount, 5)
        else:
            expected = points(amount, 1)
            if category in {"groceries", "shopping"}:
                review_status = "needs_green_qualification"
                note = "A receipt or certified-green merchant evidence is needed to establish any higher EcoCard rate."
    else:
        return {**base, "status": "unsupported_card", "expected_points": None, "actual_points": actual,
                "note": "No documented rate rule is available for this card type."}

    if review_status:
        return {**base, "status": review_status, "expected_points": expected, "actual_points": actual, "note": note}
    variance = expected - actual
    status = "match" if variance == 0 else "mismatch"
    result = {**base, "status": status, "expected_points": expected, "actual_points": actual,
              "variance_points": variance}
    if status == "mismatch":
        result["variance_value_dollars"] = format(Decimal(variance) / Decimal(100), ".2f")
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload["transactions"]
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}))
        return
    results = [audit(item if isinstance(item, dict) else {}) for item in transactions]
    summary = {}
    for result in results:
        summary[result["status"]] = summary.get(result["status"], 0) + 1
    print(json.dumps({"results": results, "summary": summary}, separators=(",", ":")))

if __name__ == "__main__":
    main()
