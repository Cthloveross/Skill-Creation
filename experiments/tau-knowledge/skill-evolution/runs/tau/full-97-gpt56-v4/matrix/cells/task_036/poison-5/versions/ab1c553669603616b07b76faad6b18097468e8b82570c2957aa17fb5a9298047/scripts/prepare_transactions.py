#!/usr/bin/env python3
"""Filter and order transaction records from the standard banking tool text.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the public schema. This module intentionally has no network or bank side effects.
"""
import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

FIELD_RE = re.compile(r"^\s{3}([a-z_]+):\s*(.*?)\s*$", re.MULTILINE)
RECORD_RE = re.compile(
    r"^\s*\d+\.\s+Record ID:\s*([^\n]+)\n(.*?)(?=^\s*\d+\.\s+Record ID:|\Z)",
    re.MULTILINE | re.DOTALL,
)


def parse_records(text: str) -> List[Dict[str, str]]:
    """Parse individual records in the documented multiline tool-result format."""
    records: List[Dict[str, str]] = []
    for match in RECORD_RE.finditer(text):
        record: Dict[str, str] = {"record_id": match.group(1).strip()}
        for key, value in FIELD_RE.findall(match.group(2)):
            record[key] = value.strip()
        records.append(record)
    return records


def parse_limit(value: Any) -> Optional[int]:
    """Return None for all; otherwise validate and return a positive limit."""
    if isinstance(value, str) and value.strip().lower() == "all":
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        limit = value
    elif isinstance(value, str) and value.strip().isdigit():
        limit = int(value.strip())
    else:
        raise ValueError("limit must be 'all' or a positive integer")
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    return limit


def date_key(record: Dict[str, str]) -> datetime:
    try:
        return datetime.strptime(record["transaction_date"], "%m/%d/%Y")
    except (KeyError, ValueError) as exc:
        raise ValueError("a matching transaction has an invalid transaction_date") from exc


def select_transactions(text: str, card_type: str, limit: Any) -> List[Dict[str, str]]:
    """Return deduplicated matching transactions in descending transaction-date order."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("transactions_text must be a nonempty tool result string")
    if not isinstance(card_type, str) or not card_type.strip():
        raise ValueError("card_type must be a nonempty string")
    requested = card_type.strip()
    parsed_limit = parse_limit(limit)
    seen = set()
    selected: List[Dict[str, str]] = []
    for record in parse_records(text):
        if record.get("credit_card_type") != requested:
            continue
        txn_id = record.get("transaction_id") or record["record_id"]
        if txn_id in seen:
            continue
        required = ("transaction_date", "merchant_name", "transaction_amount", "category", "status")
        if any(not record.get(field) for field in required):
            raise ValueError("a matching transaction is missing a required display field")
        date_key(record)  # validate before output
        seen.add(txn_id)
        selected.append({
            "transaction_id": txn_id,
            "transaction_date": record["transaction_date"],
            "merchant_name": record["merchant_name"],
            "transaction_amount": record["transaction_amount"],
            "category": record["category"],
            "status": record["status"],
        })
    # Python sort is stable, so records with the same date retain source order.
    selected.sort(key=date_key, reverse=True)
    return selected if parsed_limit is None else selected[:parsed_limit]


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        transactions = select_transactions(
            payload.get("transactions_text"),
            payload.get("card_type"),
            payload.get("limit", "all"),
        )
        print(json.dumps({
            "ok": True,
            "transactions": transactions,
            "shown_count": len(transactions),
        }, ensure_ascii=False))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "transactions": [], "shown_count": 0, "error": str(exc)}))


if __name__ == "__main__":
    main()
