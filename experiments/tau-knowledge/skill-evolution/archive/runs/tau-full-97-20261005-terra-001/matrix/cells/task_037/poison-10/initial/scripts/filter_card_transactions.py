#!/usr/bin/env python3
"""Filter and order card transaction objects supplied as JSON on stdin.

This helper is intentionally read-only. It does not call banking tools or write files.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")
DEFAULT_POSTED = ("COMPLETED", "POSTED")


def fail(message):
    return {"ok": False, "error": message}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")


def parse_amount(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a monetary value")
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"{field} must be a monetary value")


def money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    transactions = payload.get("transactions")
    card_type = payload.get("card_type")
    if not isinstance(transactions, list):
        return fail("transactions must be an array")
    if not isinstance(card_type, str) or not card_type.strip():
        return fail("card_type must be a nonempty exact card type")

    try:
        start = parse_date(payload["start_date"], "start_date") if payload.get("start_date") is not None else None
        end = parse_date(payload["end_date"], "end_date") if payload.get("end_date") is not None else None
        if start and end and start > end:
            return fail("start_date must not be after end_date")
        min_amount = parse_amount(payload["min_amount"], "min_amount") if payload.get("min_amount") is not None else None
        max_amount = parse_amount(payload["max_amount"], "max_amount") if payload.get("max_amount") is not None else None
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            return fail("min_amount must not exceed max_amount")
    except ValueError as exc:
        return fail(str(exc))

    limit = payload.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        return fail("limit must be a positive integer")

    statuses = payload.get("posted_statuses", list(DEFAULT_POSTED))
    if not isinstance(statuses, list) or not all(isinstance(x, str) and x.strip() for x in statuses):
        return fail("posted_statuses must be an array of nonempty strings")
    allowed_statuses = {x.strip().upper() for x in statuses}
    merchant_filter = payload.get("merchant_contains")
    if merchant_filter is not None and not isinstance(merchant_filter, str):
        return fail("merchant_contains must be a string")
    merchant_filter = (merchant_filter or "").casefold()

    selected = []
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            return fail(f"transactions[{index}] must be an object")
        if transaction.get("credit_card_type") != card_type:
            continue
        status = transaction.get("status")
        if not isinstance(status, str) or status.strip().upper() not in allowed_statuses:
            continue
        try:
            tx_date = parse_date(transaction.get("transaction_date"), f"transactions[{index}].transaction_date")
            amount = parse_amount(transaction.get("transaction_amount"), f"transactions[{index}].transaction_amount")
        except ValueError as exc:
            return fail(str(exc))
        merchant = transaction.get("merchant_name", "")
        if merchant_filter and merchant_filter not in str(merchant).casefold():
            continue
        if start and tx_date < start:
            continue
        if end and tx_date > end:
            continue
        if min_amount is not None and amount < min_amount:
            continue
        if max_amount is not None and amount > max_amount:
            continue
        item = dict(transaction)
        item["parsed_date"] = tx_date.isoformat()
        item["parsed_amount"] = money(amount)
        selected.append((tx_date, amount, item))

    selected.sort(key=lambda row: row[0], reverse=True)
    matched_count = len(selected)
    if limit is not None:
        selected = selected[:limit]
    output_transactions = [row[2] for row in selected]
    total = sum((row[1] for row in selected), Decimal("0"))
    return {
        "ok": True,
        "filters": {
            "card_type": card_type,
            "start_date": start.isoformat() if start else None,
            "end_date": end.isoformat() if end else None,
            "merchant_contains": payload.get("merchant_contains"),
            "min_amount": money(min_amount) if min_amount is not None else None,
            "max_amount": money(max_amount) if max_amount is not None else None,
            "posted_statuses": sorted(allowed_statuses),
            "limit": limit,
        },
        "matched_count": matched_count,
        "displayed_count": len(output_transactions),
        "display_total": money(total),
        "transactions": output_transactions,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), ensure_ascii=False))
    except json.JSONDecodeError:
        print(json.dumps(fail("stdin must contain one valid JSON object")))
    except Exception as exc:
        print(json.dumps(fail(f"unexpected processing error: {exc}")))
