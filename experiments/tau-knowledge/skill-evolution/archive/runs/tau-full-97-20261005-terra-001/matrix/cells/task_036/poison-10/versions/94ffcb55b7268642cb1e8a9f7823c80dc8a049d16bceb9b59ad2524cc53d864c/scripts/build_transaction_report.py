#!/usr/bin/env python3
"""Build a read-only, filtered credit-card transaction report from JSON stdin."""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


class ValidationError(ValueError):
    pass


def parse_date(value, field_name):
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValidationError(f"{field_name} must use YYYY-MM-DD or MM/DD/YYYY")


def parse_amount(value, field_name):
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a decimal amount")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValidationError(f"{field_name} must be a decimal amount")
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValidationError(f"{field_name} must be a decimal amount")
    if not amount.is_finite() or amount < 0:
        raise ValidationError(f"{field_name} must be a nonnegative finite amount")
    return amount


def format_money(amount):
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${rounded:,.2f}"


def required_string(record, keys, record_number):
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    choices = " or ".join(keys)
    raise ValidationError(f"transaction {record_number} requires {choices}")


def normalize_status(value):
    return value.strip().casefold() if isinstance(value, str) else ""


def build_report(payload):
    if not isinstance(payload, dict):
        raise ValidationError("input must be a JSON object")
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        raise ValidationError("card_type must be a nonempty string")
    card_type = card_type.strip()
    transactions = payload.get("transactions")
    if not isinstance(transactions, list):
        raise ValidationError("transactions must be an array")

    filters = payload.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise ValidationError("filters must be an object")

    start = parse_date(filters["date_start"], "filters.date_start") if "date_start" in filters else None
    end = parse_date(filters["date_end"], "filters.date_end") if "date_end" in filters else None
    if start and end and start > end:
        raise ValidationError("filters.date_start cannot be after filters.date_end")

    merchant_filter = filters.get("merchant")
    if merchant_filter is not None and not isinstance(merchant_filter, str):
        raise ValidationError("filters.merchant must be a string")
    merchant_filter = merchant_filter.strip().casefold() if merchant_filter else None

    minimum = parse_amount(filters["min_amount"], "filters.min_amount") if "min_amount" in filters else None
    maximum = parse_amount(filters["max_amount"], "filters.max_amount") if "max_amount" in filters else None
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValidationError("filters.min_amount cannot exceed filters.max_amount")

    posted_only = filters.get("posted_only", True)
    if not isinstance(posted_only, bool):
        raise ValidationError("filters.posted_only must be a boolean")
    statuses = filters.get("statuses")
    if statuses is not None:
        if not isinstance(statuses, list) or not all(isinstance(s, str) and s.strip() for s in statuses):
            raise ValidationError("filters.statuses must be an array of nonempty strings")
        allowed_statuses = {s.strip().casefold() for s in statuses}
    else:
        allowed_statuses = None

    limit = payload.get("limit")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
        raise ValidationError("limit must be a positive integer")

    selected = []
    requested_card_key = card_type.casefold()
    non_posted = {"pending", "authorized", "authorised", "processing"}
    for index, raw in enumerate(transactions, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"transaction {index} must be an object")
        record_card = required_string(raw, ("credit_card_type", "card_type"), index)
        if record_card.casefold() != requested_card_key:
            continue
        date_text = required_string(raw, ("transaction_date", "date"), index)
        date = parse_date(date_text, f"transaction {index}.transaction_date")
        merchant = required_string(raw, ("merchant_descriptor", "merchant_name"), index)
        amount_value = raw.get("transaction_amount", raw.get("amount"))
        if amount_value is None:
            raise ValidationError(f"transaction {index} requires transaction_amount or amount")
        amount = parse_amount(amount_value, f"transaction {index}.transaction_amount")
        status = normalize_status(raw.get("status"))
        if posted_only and status in non_posted:
            continue
        if allowed_statuses is not None and status not in allowed_statuses:
            continue
        if start and date < start:
            continue
        if end and date > end:
            continue
        if merchant_filter and merchant_filter not in merchant.casefold():
            continue
        if minimum is not None and amount < minimum:
            continue
        if maximum is not None and amount > maximum:
            continue
        selected.append({
            "date": date.isoformat(),
            "merchant_descriptor": merchant,
            "posted_amount": format_money(amount),
            "_amount": amount,
            "transaction_id": raw.get("transaction_id"),
            "category": raw.get("category"),
            "status": raw.get("status"),
        })

    selected.sort(key=lambda item: item["date"], reverse=True)
    if limit is not None:
        selected = selected[:limit]
    total = sum((item["_amount"] for item in selected), Decimal("0"))
    output_transactions = []
    for item in selected:
        output_transactions.append({key: value for key, value in item.items() if key != "_amount" and value is not None})

    return {
        "ok": True,
        "report": {
            "card_type": card_type,
            "filters": {
                "date_start": start.isoformat() if start else None,
                "date_end": end.isoformat() if end else None,
                "merchant": merchant_filter,
                "min_amount": format_money(minimum) if minimum is not None else None,
                "max_amount": format_money(maximum) if maximum is not None else None,
                "posted_only": posted_only,
                "statuses": sorted(allowed_statuses) if allowed_statuses is not None else None,
                "limit": limit,
            },
            "transaction_count": len(output_transactions),
            "total_posted_amount": format_money(total),
            "transactions": output_transactions,
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
        result = build_report(payload)
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": f"invalid JSON: {exc.msg}"}), file=sys.stdout)
        return 2
    except ValidationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stdout)
        return 2


if __name__ == "__main__":
    sys.exit(main())
