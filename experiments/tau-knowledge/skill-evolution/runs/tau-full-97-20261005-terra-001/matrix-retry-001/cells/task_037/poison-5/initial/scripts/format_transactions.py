#!/usr/bin/env python3
"""Filter and summarize normalized credit-card transaction data.

Reads one JSON object from stdin and emits one JSON object on stdout. See SKILL.md
for the schema. Uses only the Python standard library.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def fail(message):
    print(json.dumps({"error": message}))
    raise SystemExit(2)


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")


def parse_amount(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be numeric")
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        raise ValueError(f"{field} is not a valid amount")


def parse_points(value):
    if value is None or value == "":
        return None
    cleaned = str(value).strip().lower().replace("points", "").replace("point", "").replace(",", "").strip()
    try:
        result = Decimal(cleaned)
    except InvalidOperation:
        return None
    return result if result == result.to_integral_value() else None


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    card = payload.get("requested_card_type")
    raw_transactions = payload.get("transactions")
    if not isinstance(card, str) or not card.strip():
        raise ValueError("requested_card_type is required")
    if not isinstance(raw_transactions, list):
        raise ValueError("transactions must be an array")

    start = parse_date(payload["date_from"], "date_from") if payload.get("date_from") else None
    end = parse_date(payload["date_to"], "date_to") if payload.get("date_to") else None
    if start and end and start > end:
        raise ValueError("date_from must not be after date_to")
    limit = payload.get("limit", 0)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")

    matched = []
    wanted = card.strip().casefold()
    for index, item in enumerate(raw_transactions):
        if not isinstance(item, dict):
            raise ValueError(f"transactions[{index}] must be an object")
        item_card = item.get("credit_card_type")
        if not isinstance(item_card, str):
            raise ValueError(f"transactions[{index}].credit_card_type is required")
        if item_card.strip().casefold() != wanted:
            continue
        for key in ("transaction_id", "merchant_name", "transaction_date", "transaction_amount"):
            if item.get(key) is None or str(item[key]).strip() == "":
                raise ValueError(f"transactions[{index}].{key} is required")
        txn_date = parse_date(item["transaction_date"], f"transactions[{index}].transaction_date")
        if (start and txn_date < start) or (end and txn_date > end):
            continue
        amount = parse_amount(item["transaction_amount"], f"transactions[{index}].transaction_amount")
        record = {
            "transaction_id": str(item["transaction_id"]),
            "date": txn_date.strftime("%m/%d/%Y"),
            "merchant": str(item["merchant_name"]),
            "amount": money(amount),
        }
        for source, destination in (("category", "category"), ("status", "status")):
            if item.get(source) not in (None, ""):
                record[destination] = str(item[source])
        points = parse_points(item.get("rewards_earned"))
        if points is not None:
            record["rewards_earned_points"] = str(points.to_integral_value())
        matched.append((txn_date, amount, points, record))

    matched.sort(key=lambda entry: (entry[0], entry[3]["transaction_id"]), reverse=True)
    selected = matched if limit == 0 else matched[:limit]
    total = sum((entry[1] for entry in selected), Decimal("0.00"))
    dates = [entry[0] for entry in selected]
    all_points_present = bool(selected) and all(entry[2] is not None for entry in selected)
    output = {
        "requested_card_type": card,
        "matched_count": len(matched),
        "shown_count": len(selected),
        "truncated": len(selected) < len(matched),
        "shown_date_range": None if not dates else {
            "newest": max(dates).strftime("%m/%d/%Y"),
            "oldest": min(dates).strftime("%m/%d/%Y"),
        },
        "total_amount": money(total),
        "transactions": [entry[3] for entry in selected],
    }
    if all_points_present:
        output["total_rewards_points"] = str(sum(entry[2] for entry in selected).to_integral_value())
    return output


if __name__ == "__main__":
    try:
        main_input = json.load(sys.stdin)
        print(json.dumps(main(main_input), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        fail(str(exc))
