#!/usr/bin/env python3
"""Create a deterministic, card-specific transaction summary from JSON stdin."""

import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = re.compile(r"^\s*\$?\s*([+-]?[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*$")


def parse_amount(value):
    """Return Decimal for a conventional displayed dollar amount, or None."""
    if isinstance(value, (int, float)):
        # Convert through text to avoid binary arithmetic in totals.
        value = str(value)
    if not isinstance(value, str):
        return None
    match = MONEY.match(value)
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except InvalidOperation:
        return None


def money(value):
    return "${:,.2f}".format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y")
    except ValueError:
        return None


def main(payload):
    if not isinstance(payload, dict):
        return {"error": "input must be a JSON object"}
    card_type = payload.get("card_type")
    transactions = payload.get("transactions")
    if not isinstance(card_type, str) or not card_type.strip():
        return {"error": "card_type must be a nonempty string"}
    if not isinstance(transactions, list):
        return {"error": "transactions must be an array"}
    limit = payload.get("limit", 10)
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return {"error": "limit must be a positive integer"}

    target = card_type.strip().casefold()
    selected = []
    warnings = []
    for index, txn in enumerate(transactions):
        if not isinstance(txn, dict):
            warnings.append("transaction at index {} is not an object".format(index))
            continue
        txn_card = txn.get("credit_card_type")
        if not isinstance(txn_card, str) or txn_card.strip().casefold() != target:
            continue
        copied = dict(txn)
        parsed_date = parse_date(copied.get("transaction_date"))
        parsed_amount = parse_amount(copied.get("transaction_amount"))
        if parsed_date is None:
            warnings.append("matching transaction at index {} has an invalid transaction_date".format(index))
        if parsed_amount is None:
            warnings.append("matching transaction at index {} has an invalid transaction_amount".format(index))
        selected.append((parsed_date, parsed_amount, index, copied))

    # Valid dated records first, descending; preserve input order for equal/invalid dates.
    selected.sort(
        key=lambda item: (item[0] is not None, item[0] or datetime.min, -item[2]),
        reverse=True,
    )
    all_total = sum((item[1] for item in selected if item[1] is not None), Decimal("0.00"))
    recent = selected[:limit]
    recent_total = sum((item[1] for item in recent if item[1] is not None), Decimal("0.00"))

    return {
        "card_type": card_type,
        "matching_transaction_count": len(selected),
        "recent_transaction_count": len(recent),
        "recent_total": money(recent_total),
        "all_matching_total": money(all_total),
        "recent_transactions": [item[3] for item in recent],
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), ensure_ascii=False, sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid JSON input: {}".format(exc.msg)}))
    except Exception as exc:  # Keep the stdin/stdout interface machine-readable.
        print(json.dumps({"error": "unexpected processing error: {}".format(str(exc))}))
