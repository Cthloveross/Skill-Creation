#!/usr/bin/env python3
"""Filter and summarize text returned by get_credit_card_transactions_by_user.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. This module uses only the Python standard library.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"


def fail(message):
    print(json.dumps({"transactions": [], "transaction_count": 0,
                      "total_amount": "0.00", "errors": [message]}))
    return 1


def parse_date(value, field):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(field + " must be an MM/DD/YYYY string")
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        raise ValueError(field + " must use MM/DD/YYYY")


def money(value):
    cleaned = value.replace("$", "").replace(",", "").strip()
    amount = Decimal(cleaned)
    return amount.quantize(Decimal("0.01"))


def field(block, name):
    match = re.search(r"^\s*" + re.escape(name) + r":\s*(.*?)\s*$", block,
                      re.MULTILINE)
    return match.group(1) if match else None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        return fail("invalid input JSON: " + str(exc))
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    raw = payload.get("raw_transactions")
    card_type = payload.get("card_type")
    if not isinstance(raw, str) or not raw.strip():
        return fail("raw_transactions must be a nonempty string")
    if not isinstance(card_type, str) or not card_type.strip():
        return fail("card_type must be a nonempty string")
    try:
        start = parse_date(payload.get("start_date"), "start_date")
        end = parse_date(payload.get("end_date"), "end_date")
        if start and end and start > end:
            raise ValueError("start_date cannot be after end_date")
    except ValueError as exc:
        return fail(str(exc))

    # Each tool record starts with a numbered record header. Split only on that header.
    blocks = re.split(r"(?m)^\s*\d+\.\s+Record ID:\s*", raw)[1:]
    records = []
    malformed = 0
    for block in blocks:
        record_card = field(block, "credit_card_type")
        if record_card != card_type:
            continue
        txn_date = field(block, "transaction_date")
        amount_text = field(block, "transaction_amount")
        merchant = field(block, "merchant_name")
        if not txn_date or not amount_text or not merchant:
            malformed += 1
            continue
        try:
            date_obj = parse_date(txn_date, "transaction_date")
            amount = money(amount_text)
        except (ValueError, InvalidOperation):
            malformed += 1
            continue
        if (start and date_obj < start) or (end and date_obj > end):
            continue
        records.append({
            "transaction_id": field(block, "transaction_id"),
            "transaction_date": txn_date,
            "merchant_name": merchant,
            "transaction_amount": format(amount, ".2f"),
            "category": field(block, "category"),
            "status": field(block, "status"),
            "credit_card_type": record_card,
            "_date": date_obj,
            "_amount": amount,
        })

    records.sort(key=lambda item: (item["_date"], item["transaction_id"] or ""), reverse=True)
    total = sum((item["_amount"] for item in records), Decimal("0.00"))
    for item in records:
        del item["_date"]
        del item["_amount"]
    errors = []
    if malformed:
        errors.append(str(malformed) + " matching record(s) were skipped because required fields were malformed")
    print(json.dumps({
        "card_type": card_type,
        "transactions": records,
        "transaction_count": len(records),
        "total_amount": format(total.quantize(Decimal("0.01")), ".2f"),
        "errors": errors,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
