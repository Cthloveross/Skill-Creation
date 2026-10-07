#!/usr/bin/env python3
"""Calculate documented ATM bank fees from normalized review records.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
script performs no banking operations and intentionally does not attempt to
infer ATM operator surcharges or match raw transaction descriptions.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
VALID_PRODUCTS = {"blue", "green", "light_green"}
VALID_CATEGORIES = {"domestic_out_of_network", "foreign", "in_network"}


def money(value):
    """Parse a non-negative monetary input exactly and round to cents."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("must be a decimal monetary value")
    if not amount.is_finite() or amount < 0:
        raise ValueError("must be a non-negative finite monetary value")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def positive_money(value, field):
    amount = money(value)
    if amount <= 0:
        raise ValueError(field + " must be greater than zero")
    return amount


def format_money(amount):
    return format(amount.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            pass
    raise ValueError("date must be YYYY-MM-DD or MM/DD/YYYY")


def expected_fee(product, category, amount, light_oon_number=None):
    if category == "in_network":
        return Decimal("0.00")
    if product == "blue":
        if category == "domestic_out_of_network":
            return min(amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        return max(amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP)
    if product == "green":
        if category == "domestic_out_of_network":
            return Decimal("3.00")
        return max(amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP)
    # light_green
    if category == "domestic_out_of_network":
        return Decimal("0.00") if light_oon_number <= 4 else Decimal("1.50")
    if amount <= Decimal("100.00"):
        return Decimal("2.00")
    if amount <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def fail(message):
    print(json.dumps({"ok": False, "error": message}, separators=(",", ":")))


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        product = payload.get("account_product")
        if product not in VALID_PRODUCTS:
            raise ValueError("account_product must be blue, green, or light_green")
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")

        normalized = []
        for index, record in enumerate(transactions):
            if not isinstance(record, dict):
                raise ValueError("transactions[%d] must be an object" % index)
            category = record.get("category")
            if category not in VALID_CATEGORIES:
                raise ValueError("transactions[%d].category is invalid" % index)
            date = parse_date(record.get("date"))
            amount = positive_money(record.get("withdrawal_usd"), "transactions[%d].withdrawal_usd" % index)
            sequence = record.get("sequence", index)
            if not isinstance(sequence, int) or isinstance(sequence, bool):
                raise ValueError("transactions[%d].sequence must be an integer" % index)
            actual = None
            if "bank_fee" in record and record["bank_fee"] is not None:
                actual = money(record["bank_fee"])
            normalized.append({
                "index": index,
                "id": record.get("id", str(index)),
                "date": date,
                "date_input": record["date"],
                "sequence": sequence,
                "category": category,
                "amount": amount,
                "actual": actual,
            })

        # Light Green's free domestic out-of-network count restarts each calendar month.
        monthly_counts = {}
        for row in sorted(normalized, key=lambda x: (x["date"], x["sequence"], x["index"])):
            if product == "light_green" and row["category"] == "domestic_out_of_network":
                key = (row["date"].year, row["date"].month)
                monthly_counts[key] = monthly_counts.get(key, 0) + 1
                row["light_oon_number"] = monthly_counts[key]
            else:
                row["light_oon_number"] = None

        result_rows = []
        refund_total = Decimal("0.00")
        for row in normalized:  # preserve caller record order in output
            expected = expected_fee(product, row["category"], row["amount"], row["light_oon_number"])
            output = {
                "id": row["id"],
                "date": row["date_input"],
                "category": row["category"],
                "withdrawal_usd": format_money(row["amount"]),
                "expected_bank_fee": format_money(expected),
            }
            if row["light_oon_number"] is not None:
                output["monthly_domestic_out_of_network_number"] = row["light_oon_number"]
            if row["actual"] is None:
                output["actual_bank_fee"] = None
                output["overcharge"] = None
                output["review_status"] = "unpaired_bank_fee"
            else:
                difference = (row["actual"] - expected).quantize(CENT, rounding=ROUND_HALF_UP)
                overcharge = max(difference, Decimal("0.00"))
                output["actual_bank_fee"] = format_money(row["actual"])
                output["difference_actual_minus_expected"] = format_money(difference)
                output["overcharge"] = format_money(overcharge)
                output["review_status"] = "possible_overcharge" if overcharge > 0 else "no_overcharge"
                refund_total += overcharge
            result_rows.append(output)

        response = {
            "ok": True,
            "account_product": product,
            "transactions": result_rows,
            "recommended_fee_refund_total": format_money(refund_total),
            "important": "This total includes only supplied bank-fee observations that exceed the documented product fee. Confirm ownership, transaction pairing, settlement amount, prior refunds, and eligibility before any credit. Operator fees and membership reimbursements are excluded.",
        }
        print(json.dumps(response, separators=(",", ":")))
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        fail(str(exc))


if __name__ == "__main__":
    main()
