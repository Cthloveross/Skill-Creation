#!/usr/bin/env python3
"""Filter and summarize supplied credit-card transaction records.

Input and output are JSON objects on stdin/stdout. This script is read-only and
has no dependency on banking tools or external packages.
"""

import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y")
MONEY_RE = re.compile(r"^[+-]?\d+(?:\.\d{1,2})?$")


def fail(errors):
    return {"ok": False, "errors": errors}


def parse_date(value, field_name):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a date string")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field_name} must use YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value, field_name):
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a monetary amount")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
    else:
        raise ValueError(f"{field_name} must be a monetary amount")
    if not MONEY_RE.fullmatch(text):
        raise ValueError(f"{field_name} is not a valid two-decimal monetary amount")
    try:
        return Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} is not a valid monetary amount") from exc


def money_string(amount):
    return f"${amount:,.2f}"


def require_string(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required and must be a nonempty string")
    return value.strip()


def normalize_transaction(record, requested_card, expected_user_id, index):
    if not isinstance(record, dict):
        raise ValueError(f"transactions[{index}] must be an object")

    card_type = require_string(record.get("credit_card_type"), f"transactions[{index}].credit_card_type")
    if card_type.casefold() != requested_card.casefold():
        return None

    record_user_id = record.get("user_id")
    if record_user_id is not None:
        record_user_id = require_string(record_user_id, f"transactions[{index}].user_id")
        if record_user_id != expected_user_id:
            raise ValueError(f"transactions[{index}] belongs to a different user")

    transaction_day = parse_date(record.get("transaction_date"), f"transactions[{index}].transaction_date")
    amount = parse_money(record.get("transaction_amount"), f"transactions[{index}].transaction_amount")
    merchant = require_string(record.get("merchant_name"), f"transactions[{index}].merchant_name")

    result = {
        "transaction_id": record.get("transaction_id") or record.get("id"),
        "user_id": record_user_id,
        "card_type": card_type,
        "date": transaction_day.isoformat(),
        "merchant": merchant,
        "amount": money_string(amount),
        "amount_cents": int(amount * 100),
        "category": record.get("category") or "Unspecified",
        "status": record.get("status") or "Unspecified",
    }
    if "rewards_earned" in record:
        result["rewards_earned"] = record["rewards_earned"]
    return transaction_day, amount, result


def main(payload):
    if not isinstance(payload, dict):
        return fail(["input must be a JSON object"])

    try:
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array")
        requested_card = require_string(payload.get("card_type"), "card_type")
        expected_user_id = require_string(payload.get("expected_user_id"), "expected_user_id")

        start = parse_date(payload["start_date"], "start_date") if payload.get("start_date") else None
        end = parse_date(payload["end_date"], "end_date") if payload.get("end_date") else None
        if start and end and start > end:
            raise ValueError("start_date must not be after end_date")

        limit = payload.get("recent_limit", 10)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
            raise ValueError("recent_limit must be an integer from 1 through 1000")

        filtered = []
        for index, record in enumerate(transactions):
            normalized = normalize_transaction(record, requested_card, expected_user_id, index)
            if normalized is None:
                continue
            transaction_day, amount, output_record = normalized
            if start and transaction_day < start:
                continue
            if end and transaction_day > end:
                continue
            filtered.append((transaction_day, amount, output_record))

        filtered.sort(key=lambda item: (item[0], str(item[2].get("transaction_id") or "")), reverse=True)
        displayed = filtered[:limit]

        matching_total = sum((item[1] for item in filtered), Decimal("0.00"))
        displayed_total = sum((item[1] for item in displayed), Decimal("0.00"))
        category_totals = {}
        for _, amount, item in displayed:
            category = str(item["category"])
            category_totals[category] = category_totals.get(category, Decimal("0.00")) + amount

        output_rows = []
        for _, _, item in displayed:
            item = dict(item)
            item.pop("amount_cents", None)
            output_rows.append(item)

        return {
            "ok": True,
            "card_type": requested_card,
            "expected_user_id": expected_user_id,
            "scope": {
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "recent_limit": limit,
            },
            "matching_count": len(filtered),
            "returned_count": len(output_rows),
            "truncated": len(filtered) > len(output_rows),
            "matching_total": money_string(matching_total),
            "returned_total": money_string(displayed_total),
            "returned_category_totals": {
                category: money_string(category_totals[category])
                for category in sorted(category_totals, key=str.casefold)
            },
            "transactions": output_rows,
        }
    except ValueError as exc:
        return fail([str(exc)])


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        result = fail([f"invalid JSON input: {exc.msg}"])
    except Exception as exc:  # stdin failures still receive structured output
        result = fail([f"unable to read input: {exc}"])
    else:
        result = main(raw)
    json.dump(result, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
