#!/usr/bin/env python3
"""Filter and summarize supplied credit-card transaction records.

Input JSON:
  card_type (str, required)
  transactions (list[object], optional) OR raw_result (str, optional)
  start_date/end_date (optional MM/DD/YYYY or YYYY-MM-DD, inclusive)
  limit (optional positive integer)
Output JSON:
  {ok, card_type, date_range, count, total, records, rendered_lines}
  or {ok: false, error: str}.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


def value_after(block, key):
    match = re.search(r"^\s*" + re.escape(key) + r":\s*(.*?)\s*$", block, re.MULTILINE)
    return match.group(1) if match else None


def parse_raw_result(text):
    """Parse the line-oriented records returned by the declared transaction tool."""
    blocks = re.split(r"\n\s*\d+\.\s+Record ID:\s*", "\n" + text)
    records = []
    for block in blocks[1:]:
        record = {
            "transaction_id": value_after(block, "transaction_id"),
            "credit_card_type": value_after(block, "credit_card_type"),
            "merchant_name": value_after(block, "merchant_name"),
            "transaction_amount": value_after(block, "transaction_amount"),
            "transaction_date": value_after(block, "transaction_date"),
            "category": value_after(block, "category"),
            "status": value_after(block, "status"),
            "rewards_earned": value_after(block, "rewards_earned"),
        }
        if record["transaction_id"] or record["credit_card_type"]:
            records.append({k: v for k, v in record.items() if v is not None})
    return records


def parse_date(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " must be a date string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(label + " must use MM/DD/YYYY or YYYY-MM-DD")


def parse_amount(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("transaction_amount is missing or invalid")
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("invalid transaction_amount: " + value) from exc


def normalized(value):
    return value.strip().casefold() if isinstance(value, str) else ""


def main(payload):
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        raise ValueError("card_type is required")

    has_records = "transactions" in payload
    has_raw = "raw_result" in payload
    if has_records == has_raw:
        raise ValueError("provide exactly one of transactions or raw_result")
    if has_records:
        source = payload["transactions"]
        if not isinstance(source, list) or not all(isinstance(item, dict) for item in source):
            raise ValueError("transactions must be a list of objects")
    else:
        if not isinstance(payload["raw_result"], str):
            raise ValueError("raw_result must be a string")
        source = parse_raw_result(payload["raw_result"])

    start = parse_date(payload["start_date"], "start_date") if payload.get("start_date") else None
    end = parse_date(payload["end_date"], "end_date") if payload.get("end_date") else None
    if start and end and start > end:
        raise ValueError("start_date cannot be after end_date")
    limit = payload.get("limit")
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ValueError("limit must be a positive integer when provided")

    matches = []
    for item in source:
        if normalized(item.get("credit_card_type")) != normalized(card_type):
            continue
        try:
            date = parse_date(item.get("transaction_date"), "transaction_date")
            amount = parse_amount(item.get("transaction_amount"))
        except ValueError:
            # A malformed matching record cannot safely be presented or totalled.
            continue
        if (start and date < start) or (end and date > end):
            continue
        record = {
            "transaction_id": item.get("transaction_id"),
            "date": date.strftime("%m/%d/%Y"),
            "merchant": item.get("merchant_name", ""),
            "amount": format(amount.quantize(Decimal("0.01")), ".2f"),
            "category": item.get("category"),
            "status": item.get("status"),
            "rewards_earned": item.get("rewards_earned"),
            "_date": date,
            "_amount": amount,
        }
        matches.append(record)

    matches.sort(key=lambda row: row["_date"], reverse=True)
    if limit:
        matches = matches[:limit]
    total = sum((row["_amount"] for row in matches), Decimal("0"))
    records = []
    lines = []
    for row in matches:
        public = {key: value for key, value in row.items() if not key.startswith("_")}
        records.append(public)
        details = [row["date"], row["merchant"] or "Unknown merchant", "$" + row["amount"]]
        if row["category"]:
            details.append(str(row["category"]))
        if row["status"]:
            details.append(str(row["status"]))
        lines.append(" — ".join(details))

    date_range = {
        "start_date": start.strftime("%m/%d/%Y") if start else None,
        "end_date": end.strftime("%m/%d/%Y") if end else None,
    }
    return {
        "ok": True,
        "card_type": card_type.strip(),
        "date_range": date_range,
        "count": len(records),
        "total": "$" + format(total.quantize(Decimal("0.01")), ".2f"),
        "records": records,
        "rendered_lines": lines,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(incoming), ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
