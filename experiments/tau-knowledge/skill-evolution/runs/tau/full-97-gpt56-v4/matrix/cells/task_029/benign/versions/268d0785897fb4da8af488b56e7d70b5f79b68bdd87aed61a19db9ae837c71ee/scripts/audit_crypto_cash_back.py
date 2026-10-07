#!/usr/bin/env python3
"""Audit documented Crypto-Cash Back rewards.

Reads one JSON object from stdin:
  {"transactions": [transaction, ...]}
Writes one JSON report to stdout.  No network access or account actions occur.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

CARD_TYPE = "Crypto-Cash Back"
RATE = Decimal("0.02")
POINT_VALUE = Decimal("0.01")


def parse_decimal(value, field):
    """Parse a number or a monetary/points display string into Decimal."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or not numeric")
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"{field} is not numeric") from exc
    if isinstance(value, str):
        # Retain signs and decimal separator; formatted values may include $ or 'points'.
        cleaned = value.replace(",", "")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
        if not match:
            raise ValueError(f"{field} is not numeric")
        try:
            return Decimal(match.group(0))
        except InvalidOperation as exc:
            raise ValueError(f"{field} is not numeric") from exc
    raise ValueError(f"{field} is not numeric")


def money(value):
    return format(value.quantize(Decimal("0.01")), ".2f")


def audit_transaction(row):
    if not isinstance(row, dict):
        return None, {"reason": "transaction is not an object"}
    if row.get("credit_card_type") != CARD_TYPE:
        return None, {"transaction_id": row.get("transaction_id"), "reason": "not a Crypto-Cash Back transaction"}
    if str(row.get("status", "")).upper() != "COMPLETED":
        return None, {"transaction_id": row.get("transaction_id"), "reason": "transaction is not completed"}
    transaction_id = row.get("transaction_id")
    if not isinstance(transaction_id, str) or not transaction_id.strip():
        return None, {"reason": "missing transaction_id"}
    try:
        amount = parse_decimal(row.get("transaction_amount"), "transaction_amount")
        recorded = parse_decimal(row.get("rewards_earned"), "rewards_earned")
    except ValueError as exc:
        return None, {"transaction_id": transaction_id, "reason": str(exc)}
    if amount < 0:
        return None, {"transaction_id": transaction_id, "reason": "negative transaction_amount is not assessable"}
    if recorded < 0 or recorded != recorded.to_integral_value():
        return None, {"transaction_id": transaction_id, "reason": "rewards_earned must be a nonnegative whole-point value"}

    # $ amount * 2% yields cash dollars; divide by $.01 to get points (cents).
    expected = (amount * RATE / POINT_VALUE).to_integral_value(rounding=ROUND_DOWN)
    recorded_int = int(recorded)
    expected_int = int(expected)
    difference = expected_int - recorded_int
    result = {
        "transaction_id": transaction_id,
        "merchant_name": row.get("merchant_name"),
        "transaction_date": row.get("transaction_date"),
        "purchase_amount": money(amount),
        "recorded_points": recorded_int,
        "recorded_cash_value": money(Decimal(recorded_int) * POINT_VALUE),
        "expected_points": expected_int,
        "expected_cash_value": money(Decimal(expected_int) * POINT_VALUE),
        "difference_points": difference,
        "difference_cash_value": money(Decimal(difference) * POINT_VALUE),
        "matches_documented_rate": difference == 0,
    }
    return result, None


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "stdin must contain a JSON object", "detail": str(exc)}))
        return
    transactions = request.get("transactions") if isinstance(request, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "transactions must be an array"}))
        return

    audited, not_assessable, findings = [], [], []
    for row in transactions:
        result, issue = audit_transaction(row)
        if result is not None:
            audited.append(result)
            if not result["matches_documented_rate"]:
                findings.append(result)
        else:
            not_assessable.append(issue)

    totals = {
        "audited_count": len(audited),
        "finding_count": len(findings),
        "recorded_points": sum(x["recorded_points"] for x in audited),
        "expected_points": sum(x["expected_points"] for x in audited),
    }
    totals["difference_points"] = totals["expected_points"] - totals["recorded_points"]
    totals["recorded_cash_value"] = money(Decimal(totals["recorded_points"]) * POINT_VALUE)
    totals["expected_cash_value"] = money(Decimal(totals["expected_points"]) * POINT_VALUE)
    totals["difference_cash_value"] = money(Decimal(totals["difference_points"]) * POINT_VALUE)
    print(json.dumps({
        "card_type": CARD_TYPE,
        "rate_percent": "2.0",
        "rounding": "expected whole stored points are rounded down",
        "audited": audited,
        "not_assessable": not_assessable,
        "findings": findings,
        "totals": totals,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
