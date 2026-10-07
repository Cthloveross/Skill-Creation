#!/usr/bin/env python3
"""Estimate Silver Rewards Card cash back from structured transaction data.

Input JSON:
{
  "card_type": "Silver Rewards Card",
  "transactions": [
    {
      "transaction_id": str,
      "merchant_name": str (optional),
      "transaction_amount": number or currency string,
      "category": str,
      "status": str,
      "rewards_earned": number or string such as "123 points"
    }
  ]
}

Output JSON contains card_type_supported, reviewed, potential_discrepancies,
and not_final_or_unsupported. Amounts are expressed in points and in USD strings.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

POSTED_STATUSES = {"COMPLETED", "POSTED"}
BONUS_CATEGORIES = {"travel", "software", "software/saas", "saas"}


def decimal_from_value(value, field):
    """Parse a money or point value without floating point conversion."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or invalid")
    text = str(value).strip().replace(",", "")
    text = re.sub(r"^\$", "", text)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"{field} does not contain a numeric value")
    try:
        return Decimal(match.group(0))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is invalid") from exc


def usd_from_points(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), ".2f")


def estimate_transaction(tx):
    transaction_id = str(tx.get("transaction_id", "")).strip()
    if not transaction_id:
        raise ValueError("transaction_id is missing")
    amount = decimal_from_value(tx.get("transaction_amount"), "transaction_amount")
    if amount < 0:
        raise ValueError("transaction_amount cannot be negative")
    recorded_decimal = decimal_from_value(tx.get("rewards_earned"), "rewards_earned")
    if recorded_decimal < 0 or recorded_decimal != recorded_decimal.to_integral_value():
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    recorded = int(recorded_decimal)
    category = str(tx.get("category", "")).strip()
    rate = Decimal("0.04") if category.casefold() in BONUS_CATEGORIES else Decimal("0.01")
    # Cash back is a currency amount; represent its cent amount as points.
    estimated_cash = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    expected_points = int((estimated_cash * Decimal("100")).to_integral_value())
    result = {
        "transaction_id": transaction_id,
        "merchant_name": str(tx.get("merchant_name", "")).strip(),
        "category": category,
        "status": str(tx.get("status", "")).strip(),
        "transaction_amount_usd": format(amount.quantize(Decimal("0.01")), ".2f"),
        "applied_base_rate_percent": format(rate * 100, ".1f"),
        "recorded_points": recorded,
        "recorded_cash_back_usd": usd_from_points(recorded),
        "estimated_points": expected_points,
        "estimated_cash_back_usd": usd_from_points(expected_points),
        "difference_points": expected_points - recorded,
        "comparison_note": (
            "Base-rate estimate only; merchant classification, exclusions, "
            "promotions, and final rewards rules can affect review."
        ),
    }
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        card_type = str(payload.get("card_type", "")).strip()
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a JSON array")

        output = {
            "card_type": card_type,
            "card_type_supported": card_type.casefold() == "silver rewards card",
            "reviewed": [],
            "potential_discrepancies": [],
            "not_final_or_unsupported": [],
        }
        if not output["card_type_supported"]:
            output["not_final_or_unsupported"].append({
                "reason": "This helper contains documented base rates only for the Silver Rewards Card."
            })
            print(json.dumps(output, separators=(",", ":")))
            return

        for index, tx in enumerate(transactions):
            if not isinstance(tx, dict):
                output["not_final_or_unsupported"].append({
                    "index": index,
                    "reason": "Transaction entry is not an object."
                })
                continue
            status = str(tx.get("status", "")).strip().upper()
            if status not in POSTED_STATUSES:
                output["not_final_or_unsupported"].append({
                    "transaction_id": str(tx.get("transaction_id", "")).strip(),
                    "reason": "Transaction is not posted/completed; rewards may not be final."
                })
                continue
            try:
                review = estimate_transaction(tx)
            except ValueError as exc:
                output["not_final_or_unsupported"].append({
                    "transaction_id": str(tx.get("transaction_id", "")).strip(),
                    "reason": str(exc)
                })
                continue
            output["reviewed"].append(review)
            if review["difference_points"] != 0:
                output["potential_discrepancies"].append(review)

        print(json.dumps(output, separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
