#!/usr/bin/env python3
"""Filter and order a credit-card transaction tool result.

Reads one JSON object from stdin and writes one JSON object to stdout. See
SKILL.md for the public input and output schema.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List


def parse_raw_result(text: str) -> List[Dict[str, str]]:
    """Parse the line-oriented records returned by the transaction lookup tool."""
    records: List[Dict[str, str]] = []
    current: Dict[str, str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        # Tool records start like: "1. Record ID: txn_abc".
        if ". Record ID:" in line:
            prefix, record_id = line.split(". Record ID:", 1)
            if prefix.isdigit():
                if current is not None:
                    records.append(current)
                current = {"record_id": record_id.strip()}
                continue
        if current is not None and ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key and value:
                current[key] = value

    if current is not None:
        records.append(current)
    return records


def date_sort_key(record: Dict[str, Any]) -> tuple[int, datetime]:
    value = str(record.get("transaction_date", "")).strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return (1, datetime.strptime(value, pattern))
        except ValueError:
            pass
    # Invalid/missing dates go after dated transactions in descending order.
    return (0, datetime.min)


def output_error(message: str) -> None:
    print(json.dumps({"ok": False, "error": message}))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        output_error(f"stdin must contain one JSON object: {exc.msg}")
        return

    if not isinstance(payload, dict):
        output_error("input must be a JSON object")
        return

    target = payload.get("target_card_type")
    if not isinstance(target, str) or not target.strip():
        output_error("target_card_type must be a non-empty string")
        return
    target = target.strip()

    has_raw = "raw_transaction_result" in payload
    has_records = "transactions" in payload
    if has_raw == has_records:
        output_error("provide exactly one of raw_transaction_result or transactions")
        return

    if has_raw:
        raw = payload["raw_transaction_result"]
        if not isinstance(raw, str):
            output_error("raw_transaction_result must be a string")
            return
        records: List[Dict[str, Any]] = parse_raw_result(raw)
    else:
        supplied = payload["transactions"]
        if not isinstance(supplied, list) or not all(isinstance(x, dict) for x in supplied):
            output_error("transactions must be an array of objects")
            return
        records = supplied

    limit = payload.get("limit")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        output_error("limit must be a positive integer when supplied")
        return

    matched = [
        record for record in records
        if isinstance(record.get("credit_card_type"), str)
        and record["credit_card_type"].strip() == target
    ]
    matched.sort(key=date_sort_key, reverse=True)
    shown = matched if limit is None else matched[:limit]

    fields = (
        "record_id", "transaction_id", "credit_card_type", "merchant_name",
        "transaction_amount", "transaction_date", "category", "status",
        "rewards_earned",
    )
    normalized = [
        {field: record[field] for field in fields if field in record}
        for record in shown
    ]
    print(json.dumps({
        "ok": True,
        "target_card_type": target,
        "matched_count": len(matched),
        "shown_count": len(normalized),
        "transactions": normalized,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
