#!/usr/bin/env python3
"""Filter and format posted credit-card transactions.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the public input and output schema.
"""
import json
import re
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

POSTED = {"COMPLETED", "POSTED"}
DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d")


def fail(message):
    return {"ok": False, "error": message}


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    text = value.strip()
    # Accept a timestamp only when its leading portion is an ISO calendar date.
    if len(text) >= 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text[:10]):
        text = text[:10]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} has an unsupported date format: {value!r}")


def parse_amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("transaction_amount must be a monetary number or string")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip()
    else:
        raise ValueError("transaction_amount must be a monetary number or string")
    # Supports normal dollar formatting and accounting negatives such as ($12.34).
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    text = text.replace("$", "").replace(",", "").strip()
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"invalid transaction_amount: {value!r}")
    if negative:
        amount = -amount
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def money(amount):
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def field(record, *names):
    for name in names:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def main(payload):
    if not isinstance(payload, dict):
        return fail("input must be a JSON object")
    card_type = payload.get("card_type")
    transactions = payload.get("transactions")
    if not isinstance(card_type, str) or not card_type.strip():
        return fail("card_type is required")
    if not isinstance(transactions, list):
        return fail("transactions must be an array of structured records")

    try:
        explicit_start = payload.get("start_date")
        explicit_end = payload.get("end_date")
        if (explicit_start is None) != (explicit_end is None):
            return fail("provide both start_date and end_date for an explicit range")
        if explicit_start is not None:
            start = parse_date(explicit_start, "start_date")
            end = parse_date(explicit_end, "end_date")
        else:
            as_of = parse_date(payload.get("as_of"), "as_of")
            lookback = payload.get("lookback_days", 30)
            if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback < 1:
                return fail("lookback_days must be a positive integer")
            end = as_of
            start = end - timedelta(days=lookback - 1)
        if start > end:
            return fail("start_date must not be after end_date")
        limit = payload.get("limit", 25)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            return fail("limit must be a positive integer")
    except ValueError as exc:
        return fail(str(exc))

    selected = []
    target = card_type.strip().casefold()
    for index, record in enumerate(transactions):
        if not isinstance(record, dict):
            return fail(f"transactions[{index}] must be an object")
        record_card = field(record, "credit_card_type", "card_type")
        if not isinstance(record_card, str) or record_card.strip().casefold() != target:
            continue
        status = field(record, "status")
        if not isinstance(status, str) or status.strip().upper() not in POSTED:
            continue
        try:
            posted_date = parse_date(field(record, "transaction_date", "posted_date", "date"),
                                     f"transactions[{index}].transaction_date")
            amount = parse_amount(field(record, "transaction_amount", "amount", "posted_amount"))
        except ValueError as exc:
            return fail(str(exc))
        merchant = field(record, "merchant_name", "merchant", "merchant_descriptor")
        if not isinstance(merchant, str) or not merchant.strip():
            return fail(f"transactions[{index}] is missing merchant_name")
        if start <= posted_date <= end:
            category = field(record, "category")
            selected.append({
                "date": posted_date.isoformat(),
                "merchant": merchant.strip(),
                "amount": money(amount),
                "amount_decimal": str(amount),
                "category": category.strip() if isinstance(category, str) and category.strip() else None,
                "status": status.strip().upper(),
                "_amount": amount,
                "_date": posted_date,
            })

    selected.sort(key=lambda item: (item["_date"], item["merchant"].casefold()), reverse=True)
    total = sum((item["_amount"] for item in selected), Decimal("0.00"))
    shown = selected[:limit]
    output_records = []
    lines = [f"Recent posted transactions for {card_type.strip()} ({start.isoformat()} through {end.isoformat()}):"]
    if not shown:
        lines.append("No posted transactions were found in this period.")
    else:
        for item in shown:
            category = f" — {item['category']}" if item["category"] else ""
            label = " (credit/refund)" if item["_amount"] < 0 else ""
            lines.append(f"• {item['date']} — {item['merchant']}: {item['amount']}{label}{category}")
            output_records.append({key: item[key] for key in ("date", "merchant", "amount", "amount_decimal", "category", "status")})
        lines.append(f"Posted records in period: {len(selected)}. Net posted activity: {money(total)}.")
        if len(selected) > limit:
            lines.append(f"Showing the most recent {limit} of {len(selected)} records; I can provide the remainder or a different date range.")
    lines.append("This activity total may not equal the current card balance because the balance can include items outside this period, payments, fees, or other posted credits.")

    return {
        "ok": True,
        "window": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "transaction_count": len(selected),
        "net_total": money(total),
        "net_total_decimal": str(total),
        "transactions": output_records,
        "truncated": len(selected) > limit,
        "response_text": "\n".join(lines),
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        result = main(data)
    except json.JSONDecodeError as exc:
        result = fail(f"invalid JSON input: {exc.msg}")
    except Exception as exc:  # Ensure callers always receive a JSON result.
        result = fail(f"unexpected formatter error: {exc}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
