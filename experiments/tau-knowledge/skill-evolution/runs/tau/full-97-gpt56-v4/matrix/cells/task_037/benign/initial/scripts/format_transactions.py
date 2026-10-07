#!/usr/bin/env python3
"""Filter and format credit-card transaction lookup results.

Reads one JSON object from stdin and emits one JSON object on stdout. See SKILL.md
for the schema. Uses only the Python standard library.
"""
import json
import re
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def display_date(value):
    parsed = parse_date(value)
    return parsed.strftime("%m/%d/%Y") if parsed else str(value).strip()


def amount_text(value):
    """Render common numeric/currency input without altering a supplied amount."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("$"):
        return text
    try:
        number = Decimal(text.replace(",", "").replace("$", ""))
        return f"${number:,.2f}"
    except (InvalidOperation, ValueError):
        return text


def value_for(record, *names):
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return None


def parse_raw_records(text):
    """Parse the line-oriented response produced by the standard history lookup."""
    records, current = [], None
    for line in str(text).splitlines():
        record_start = re.match(r"\s*\d+\.\s+Record ID:\s*(.+?)\s*$", line)
        if record_start:
            if current:
                records.append(current)
            current = {"record_id": record_start.group(1)}
            continue
        field = re.match(r"\s+([A-Za-z_]+):\s*(.*?)\s*$", line)
        if current is not None and field:
            current[field.group(1)] = field.group(2)
    if current:
        records.append(current)
    return records


def read_records(payload):
    records = payload.get("transactions")
    if records is not None:
        if not isinstance(records, list) or not all(isinstance(x, dict) for x in records):
            raise ValueError("transactions must be a list of objects")
        return records
    if "raw_transactions" in payload:
        parsed = parse_raw_records(payload["raw_transactions"])
        if not parsed and str(payload["raw_transactions"]).strip():
            raise ValueError("could not parse any transaction records from raw_transactions")
        return parsed
    raise ValueError("provide transactions or raw_transactions")


def make_safe_record(record):
    return {
        "date": display_date(value_for(record, "transaction_date", "date")),
        "merchant": str(value_for(record, "merchant_name", "merchant", "descriptor") or "").strip(),
        "amount": amount_text(value_for(record, "transaction_amount", "amount", "posted_amount")),
        "category": str(value_for(record, "category") or "").strip(),
        "status": str(value_for(record, "status") or "UNKNOWN").strip().upper(),
    }


def main(payload):
    card_type = payload.get("card_type")
    if not isinstance(card_type, str) or not card_type.strip():
        raise ValueError("card_type is required")
    selected = card_type.strip().casefold()
    start = parse_date(payload.get("start_date")) if payload.get("start_date") else None
    end = parse_date(payload.get("end_date")) if payload.get("end_date") else None
    if payload.get("start_date") and not start:
        raise ValueError("start_date must use MM/DD/YYYY or YYYY-MM-DD")
    if payload.get("end_date") and not end:
        raise ValueError("end_date must use MM/DD/YYYY or YYYY-MM-DD")
    if start and end and start > end:
        raise ValueError("start_date cannot be after end_date")

    selected_records = []
    skipped_invalid_dates = 0
    for record in read_records(payload):
        record_card = str(value_for(record, "credit_card_type", "card_type") or "").strip().casefold()
        if record_card != selected:
            continue
        raw_date = value_for(record, "transaction_date", "date")
        parsed = parse_date(raw_date)
        if (start or end) and not parsed:
            skipped_invalid_dates += 1
            continue
        if start and parsed < start:
            continue
        if end and parsed > end:
            continue
        safe = make_safe_record(record)
        if not safe["date"] or not safe["merchant"] or not safe["amount"]:
            raise ValueError("matching transaction lacks date, merchant, or amount")
        safe["_sort_date"] = parsed or date.min
        selected_records.append(safe)

    selected_records.sort(key=lambda item: item["_sort_date"], reverse=True)
    posted = [x for x in selected_records if x["status"] == "COMPLETED"]
    nonposted = [x for x in selected_records if x["status"] != "COMPLETED"]
    for item in selected_records:
        item.pop("_sort_date", None)

    if posted:
        dates = [parse_date(x["date"]) for x in posted]
        known_dates = [x for x in dates if x]
        coverage = {
            "newest": max(known_dates).strftime("%m/%d/%Y") if known_dates else None,
            "oldest": min(known_dates).strftime("%m/%d/%Y") if known_dates else None,
        }
    else:
        coverage = {"newest": None, "oldest": None}

    title = card_type.strip()
    if posted:
        intro = f"Here are the {len(posted)} posted {title} transaction(s) returned for your requested period"
        if coverage["oldest"] and coverage["newest"]:
            intro += f" ({coverage['oldest']} through {coverage['newest']})"
        lines = [intro + ":"]
        lines += [f"- {x['date']} — {x['merchant']} — {x['amount']}" for x in posted]
    else:
        lines = [f"No posted {title} transactions were returned for your requested period."]
    if nonposted:
        lines.append("Other matching activity not presented as posted:")
        lines += [f"- {x['date']} — {x['merchant']} — {x['amount']} ({x['status'].lower()})" for x in nonposted]
    if payload.get("current_balance") is not None:
        lines.append(f"The reported current balance for this card is {amount_text(payload['current_balance'])}.")
    if skipped_invalid_dates:
        lines.append(f"{skipped_invalid_dates} matching record(s) could not be included because their date was invalid.")
    lines.append("If an entry looks unfamiliar, review its posted date and merchant descriptor before pursuing a dispute.")

    return {
        "ok": True,
        "posted_count": len(posted),
        "pending_count": len(nonposted),
        "coverage": coverage,
        "transactions": selected_records,
        "response": "\n".join(lines),
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), ensure_ascii=False))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
