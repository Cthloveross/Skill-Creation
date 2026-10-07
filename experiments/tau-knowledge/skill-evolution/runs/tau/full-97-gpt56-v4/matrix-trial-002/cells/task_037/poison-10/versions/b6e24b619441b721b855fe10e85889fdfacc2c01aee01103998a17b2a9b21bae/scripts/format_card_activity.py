#!/usr/bin/env python3
"""Filter and format card transactions. Reads one JSON object from stdin, writes JSON."""
import json
import re
import sys
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation


def parse_date(value):
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    # Tool timestamps commonly begin with an ISO date or an MM/DD/YYYY date.
    match = re.search(r"(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2})", text)
    if match and match.group(0) != text:
        return parse_date(match.group(0))
    return None


def parse_money(value):
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    cleaned = re.sub(r"[^0-9.\-]", "", str(value or ""))
    if not cleaned or cleaned in ("-", "."):
        raise InvalidOperation
    return Decimal(cleaned)


def money(value):
    return f"${value:,.2f}"


def raw_records(raw):
    """Parse the line-oriented result returned by the supplied transaction tool."""
    blocks = re.split(r"\n(?=\d+\.\s+Record ID:)", raw)
    rows = []
    for block in blocks:
        fields = {}
        for line in block.splitlines():
            match = re.match(r"^\s*([A-Za-z][A-Za-z0-9_ ]*):\s*(.*?)\s*$", line)
            if match:
                key = match.group(1).strip().lower().replace(" ", "_")
                fields[key] = match.group(2)
        if "transaction_id" in fields or "credit_card_type" in fields:
            rows.append(fields)
    return rows


def get_rows(source):
    if isinstance(source, list):
        return source
    if isinstance(source, dict):
        rows = source.get("transactions")
        if isinstance(rows, list):
            return rows
        # Permit a single structured transaction object as well.
        if "transaction_id" in source or "credit_card_type" in source:
            return [source]
        return []
    if isinstance(source, str):
        return raw_records(source)
    return []


def field(row, *names):
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return ""


def main(payload):
    card_type = str(payload.get("card_type", "")).strip()
    if not card_type:
        return {"ok": False, "error": "card_type is required"}
    source = payload.get("transactions")
    if source is None:
        return {"ok": False, "error": "transactions is required"}

    explicit_start = payload.get("start_date")
    explicit_end = payload.get("end_date")
    as_of = parse_date(payload.get("as_of"))
    if bool(explicit_start) != bool(explicit_end):
        return {"ok": False, "error": "provide both start_date and end_date for an explicit range"}
    if explicit_start:
        start, end = parse_date(explicit_start), parse_date(explicit_end)
        if not start or not end or start > end:
            return {"ok": False, "error": "dates must be valid and start_date must not be after end_date"}
    elif as_of:
        try:
            days = int(payload.get("days", 30))
        except (TypeError, ValueError):
            return {"ok": False, "error": "days must be a nonnegative integer"}
        if days < 0:
            return {"ok": False, "error": "days must be a nonnegative integer"}
        start, end = as_of - timedelta(days=days), as_of
    else:
        start = end = None

    selected, skipped = [], 0
    for row in get_rows(source):
        if not isinstance(row, dict):
            skipped += 1
            continue
        row_card = str(field(row, "credit_card_type", "card_type")).strip()
        if row_card.casefold() != card_type.casefold():
            continue
        tx_date = parse_date(field(row, "transaction_date", "date"))
        if start and (not tx_date or tx_date < start or tx_date > end):
            continue
        try:
            amount = parse_money(field(row, "transaction_amount", "amount"))
        except InvalidOperation:
            skipped += 1
            continue
        selected.append({
            "transaction_id": str(field(row, "transaction_id", "record_id")),
            "date": tx_date.strftime("%m/%d/%Y") if tx_date else str(field(row, "transaction_date", "date")),
            "_date": tx_date,
            "merchant": str(field(row, "merchant_name", "merchant")) or "Unspecified merchant",
            "amount": amount,
            "category": str(field(row, "category")),
            "status": str(field(row, "status")) or "Unspecified",
            "card_type": row_card,
        })

    selected.sort(key=lambda x: (x["_date"] or date.min, x["transaction_id"]), reverse=True)
    try:
        limit = payload.get("limit")
        limit = int(limit) if limit is not None else None
        if limit is not None and limit <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"ok": False, "error": "limit must be a positive integer when supplied"}
    matched_before_limit = len(selected)
    if limit is not None:
        selected = selected[:limit]

    posted_total = sum((x["amount"] for x in selected if x["status"].upper() == "COMPLETED"), Decimal("0"))
    public_rows = []
    lines = []
    for tx in selected:
        public = {k: v for k, v in tx.items() if k != "_date"}
        public["amount"] = money(tx["amount"])
        public_rows.append(public)
        suffix = f"; {tx['category']}" if tx["category"] else ""
        lines.append(f"{public['date']} — {public['merchant']} — {public['amount']} — {public['status']}{suffix}")

    if start:
        heading = f"{card_type} activity from {start.strftime('%m/%d/%Y')} through {end.strftime('%m/%d/%Y')}"
    else:
        heading = f"Most recent returned {card_type} activity"
    if lines:
        text = heading + ":\n" + "\n".join(lines)
        text += f"\nPosted completed-charge total shown: {money(posted_total)}."
        if matched_before_limit > len(selected):
            text += f" Showing {len(selected)} of {matched_before_limit} matching transactions."
    else:
        text = heading + ": no matching transactions were returned."

    card_matches = all(x["card_type"].casefold() == card_type.casefold() for x in selected)
    in_window = all(not start or (x["_date"] and start <= x["_date"] <= end) for x in selected)
    recomputed = sum((x["amount"] for x in selected if x["status"].upper() == "COMPLETED"), Decimal("0")) == posted_total
    return {
        "ok": True,
        "card_type": card_type,
        "window": {"start_date": start.isoformat() if start else None, "end_date": end.isoformat() if end else None},
        "matching_transactions_before_limit": matched_before_limit,
        "transactions": public_rows,
        "posted_total": money(posted_total),
        "text": text,
        "validation": {
            "card_matches": card_matches,
            "in_requested_window": in_window,
            "total_recomputes": recomputed,
            "skipped_malformed_rows": skipped,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), ensure_ascii=False, default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
