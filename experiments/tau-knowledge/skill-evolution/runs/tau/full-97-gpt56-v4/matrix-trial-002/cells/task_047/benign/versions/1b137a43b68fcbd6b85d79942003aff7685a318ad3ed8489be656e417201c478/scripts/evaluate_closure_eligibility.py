#!/usr/bin/env python3
"""Evaluate deterministic closure checks from already obtained banking data.

Reads a single JSON object from stdin and writes one JSON object to stdout.
This program never calls banking systems and never initiates a closure.
"""
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_REPLACEMENT = {"delivered", "cancelled"}
BLOCKING_DISPUTES = {"active", "open", "pending", "under_review", "under review"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def parse_balance(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("current_balance must be a number or string")
    normalized = value.strip().replace("$", "").replace(",", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", normalized):
        raise ValueError("current_balance is not numeric")
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not numeric") from exc


def as_statuses(value, field):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be an array of strings")
    return [item.strip().lower() for item in value]


def main():
    result = {"eligible": False, "checks": {}, "errors": []}
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        current = parse_date(payload.get("current_date"))
        opened = parse_date(payload.get("date_opened"))
        balance = parse_balance(payload.get("current_balance"))
        disputes = as_statuses(payload.get("dispute_statuses"), "dispute_statuses")
        replacements = as_statuses(payload.get("replacement_statuses"), "replacement_statuses")

        result["checks"] = {
            "zero_balance": balance == Decimal("0"),
            "account_age_at_least_60_days": (current - opened).days >= 60,
            "no_blocking_disputes": not any(status in BLOCKING_DISPUTES for status in disputes),
            "no_pending_replacement_orders": all(status in FINAL_REPLACEMENT for status in replacements),
        }
        result["eligible"] = all(result["checks"].values())
    except Exception as exc:  # report safe validation error instead of implying eligibility
        result["errors"].append(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
