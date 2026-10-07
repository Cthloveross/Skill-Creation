#!/usr/bin/env python3
"""Filter one card's dated transaction records.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the public input and output contract.  Standard library only.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def records(value):
    """Accept a record list or the line-oriented text returned by banking lookups."""
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    if not isinstance(value, str):
        return []
    # Each service record starts with a numbered Record ID line.  Capture its
    # indented key/value lines without depending on particular record IDs.
    chunks = re.split(r"(?m)^\s*\d+\.\s+Record ID:\s*[^\n]*\n", value)
    parsed = []
    for chunk in chunks[1:]:
        item = {}
        for line in chunk.splitlines():
            match = re.match(r"^\s{1,}([A-Za-z][A-Za-z0-9_ ]*):\s*(.*?)\s*$", line)
            if match:
                item[match.group(1).strip()] = match.group(2)
        if item:
            parsed.append(item)
    return parsed


def parse_date(value):
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("unusable transaction date: %r" % text)


def parse_as_of(value):
    text = str(value).strip()
    # Banking time displays can include a trailing timezone abbreviation that
    # datetime.fromisoformat does not universally accept.  The calendar date
    # is sufficient because transactions here contain dates, not timestamps.
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return datetime.strptime(iso.group(1), "%Y-%m-%d").date()
    us = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", text)
    if us:
        return datetime.strptime(us.group(1), "%m/%d/%Y").date()
    raise ValueError("as_of must contain a YYYY-MM-DD or MM/DD/YYYY date")


def cents(value):
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned or cleaned in {"-", ".", "-."}:
        raise ValueError("unusable transaction amount: %r" % value)
    try:
        amount = Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("unusable transaction amount: %r" % value) from exc
    return int(amount * 100)


def money(amount_cents):
    sign = "-" if amount_cents < 0 else ""
    return f"{sign}${abs(amount_cents) / 100:,.2f}"


def main(payload):
    card_type = str(payload.get("card_type", "")).strip()
    if not card_type:
        raise ValueError("card_type is required")
    try:
        days = int(payload.get("days", 30))
    except (TypeError, ValueError) as exc:
        raise ValueError("days must be a nonnegative integer") from exc
    if days < 0:
        raise ValueError("days must be a nonnegative integer")
    as_of = parse_as_of(payload.get("as_of", ""))
    start = as_of - timedelta(days=days)
    source = records(payload.get("transactions"))
    if not source:
        raise ValueError("no transaction records were supplied or parsed")

    matches, warnings = [], []
    for record in source:
        record_card = str(record.get("credit_card_type", record.get("card_type", ""))).strip()
        if record_card != card_type:
            continue
        try:
            date = parse_date(record.get("transaction_date", ""))
            amount_cents = cents(record.get("transaction_amount", ""))
        except ValueError as exc:
            warnings.append(str(exc))
            continue
        if start <= date <= as_of:
            matches.append({
                "transaction_id": record.get("transaction_id", record.get("Record ID", "")),
                "date": date.isoformat(),
                "merchant_name": record.get("merchant_name", ""),
                "amount": money(amount_cents),
                "amount_cents": amount_cents,
                "category": record.get("category", ""),
                "status": record.get("status", ""),
                "rewards_earned": record.get("rewards_earned", ""),
            })
    matches.sort(key=lambda item: (item["date"], str(item["transaction_id"])))

    balance = None
    for account in records(payload.get("accounts", [])):
        if str(account.get("card_type", "")).strip() == card_type:
            value = account.get("current_balance")
            if value not in (None, ""):
                balance = str(value)
            break
    total = sum(item["amount_cents"] for item in matches)
    return {
        "ok": True,
        "card_type": card_type,
        "window_start": start.isoformat(),
        "window_end": as_of.isoformat(),
        "window_is_inclusive": True,
        "transaction_count": len(matches),
        "transactions": matches,
        "displayed_transaction_total": money(total),
        "displayed_transaction_total_cents": total,
        "reported_current_balance": balance,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = main(payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
