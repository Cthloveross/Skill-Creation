#!/usr/bin/env python3
"""Select and format recent transactions for one verified credit-card type.

Reads one JSON object from stdin and emits one JSON object to stdout. This script
is intentionally read-only and assumes the caller has completed identity and
account-ownership verification.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REQUIRED = ("credit_card_type", "transaction_date", "merchant_name", "transaction_amount")
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def fail(message):
    return {"ok": False, "error": message}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("transaction_date must be a string")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError("transaction_date must use MM/DD/YYYY or YYYY-MM-DD")


def normalize_amount(value):
    """Validate a conventional currency input while retaining its supplied display."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        amount = Decimal(str(value))
        return f"${amount:,.2f}"
    if not isinstance(value, str) or not value.strip():
        raise ValueError("transaction_amount must be a nonempty currency value")
    raw = value.strip()
    numeric = raw.replace("$", "").replace(",", "").strip()
    try:
        Decimal(numeric)
    except InvalidOperation as exc:
        raise ValueError("transaction_amount is not a valid currency value") from exc
    return raw


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        return fail("card_type must be a nonempty string")
    target = card_type.strip().casefold()

    limit = payload.get("limit", 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        return fail("limit must be an integer from 1 through 20")

    source = payload.get("transactions")
    if not isinstance(source, list):
        return fail("transactions must be an array")

    matches = []
    for index, transaction in enumerate(source):
        if not isinstance(transaction, dict):
            return fail(f"transaction at index {index} must be an object")
        if any(field not in transaction or transaction[field] is None for field in REQUIRED):
            return fail(f"transaction at index {index} is missing a required field")
        if not isinstance(transaction["credit_card_type"], str):
            return fail(f"transaction at index {index} has an invalid credit_card_type")
        try:
            date_value = parse_date(transaction["transaction_date"])
            amount_display = normalize_amount(transaction["transaction_amount"])
        except ValueError as exc:
            return fail(f"transaction at index {index}: {exc}")
        if transaction["credit_card_type"].strip().casefold() == target:
            item = dict(transaction)
            item["transaction_amount"] = amount_display
            item["_sort_date"] = date_value
            item["_source_index"] = index
            matches.append(item)

    if not matches:
        return fail("no transactions match the requested card_type")

    # Source order is used only as a stable tie-breaker for same-date records.
    matches.sort(key=lambda item: (item["_sort_date"], item["_source_index"]), reverse=True)
    selected = matches[:limit]
    cleaned = []
    display_lines = []
    for item in selected:
        clean = {key: value for key, value in item.items() if not key.startswith("_")}
        cleaned.append(clean)
        category = clean.get("category")
        status = clean.get("status", "status not provided")
        suffix = []
        if category:
            suffix.append(f"Category: {category}")
        suffix.append(f"Status: {status}")
        display_lines.append(
            f"{clean['transaction_date']} — {clean['merchant_name']} — "
            f"{clean['transaction_amount']} ({'; '.join(suffix)})"
        )

    return {
        "ok": True,
        "card_type": card_type.strip(),
        "count": len(cleaned),
        "transactions": cleaned,
        "display_lines": display_lines,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        result = main(incoming)
    except json.JSONDecodeError:
        result = fail("stdin must contain valid JSON")
    except Exception as exc:  # Keep the script's public failure output structured.
        result = fail(f"unexpected input error: {exc}")
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
