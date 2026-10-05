#!/usr/bin/env python3
"""Evaluate deterministic credit-card closure eligibility facts from JSON stdin.

This program performs no banking actions. See SKILL.md for the input and output
schema and for the operational checks that must accompany this calculation.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

FINAL_DISPUTE_STATUSES = {"closed", "resolved"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value: Any) -> Optional[date]:
    """Parse supported account/current date representations without guessing."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    # Current-time tools commonly return an ISO-like timestamp with a timezone label.
    iso_prefix = text[:10]
    try:
        return datetime.strptime(iso_prefix, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_money(value: Any) -> Optional[Decimal]:
    """Return a decimal only for an unambiguous currency-like value."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if not isinstance(value, str):
        return None
    text = value.strip().replace(",", "")
    if text.startswith("$"):
        text = text[1:].strip()
    if not re.fullmatch(r"[+-]?\d+(?:\.\d+)?", text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def state_from_records(
    records: Any, final_statuses: set[str], label: str
) -> dict[str, str]:
    """Assess an explicitly returned list; missing/ambiguous statuses stay unknown."""
    if records is None:
        return {"state": "unknown", "detail": f"{label} lookup was unavailable"}
    if not isinstance(records, list):
        return {"state": "unknown", "detail": f"{label} result was not a list"}
    if not records:
        return {"state": "pass", "detail": f"no {label} records returned"}

    non_final: list[str] = []
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("status"), str):
            return {
                "state": "unknown",
                "detail": f"a {label} record has no usable status",
            }
        status = record["status"].strip().lower()
        if status not in final_statuses:
            non_final.append(status or "blank")
    if non_final:
        return {
            "state": "block",
            "detail": f"non-final {label} status(es): {', '.join(non_final)}",
        }
    return {"state": "pass", "detail": f"all {label} records are final"}


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    checks: dict[str, dict[str, str]] = {}

    balance = parse_money(payload.get("current_balance"))
    if balance is None:
        checks["balance"] = {"state": "unknown", "detail": "balance is missing or malformed"}
    elif balance == Decimal("0"):
        checks["balance"] = {"state": "pass", "detail": "balance is exactly zero"}
    else:
        checks["balance"] = {"state": "block", "detail": "balance is not exactly zero"}

    current_day = parse_date(payload.get("current_time"))
    opened_day = parse_date(payload.get("date_of_account_open"))
    age_days: Optional[int] = None
    if current_day is None or opened_day is None:
        checks["account_age"] = {"state": "unknown", "detail": "current date or opening date is missing or malformed"}
    else:
        age_days = (current_day - opened_day).days
        if age_days < 0:
            checks["account_age"] = {"state": "unknown", "detail": "opening date is later than current date"}
        elif age_days >= 60:
            checks["account_age"] = {"state": "pass", "detail": "account is at least 60 days old"}
        else:
            checks["account_age"] = {"state": "block", "detail": "account is less than 60 days old"}

    checks["disputes"] = state_from_records(
        payload.get("disputes"), FINAL_DISPUTE_STATUSES, "dispute"
    )
    checks["replacement_orders"] = state_from_records(
        payload.get("replacement_orders"), FINAL_REPLACEMENT_STATUSES, "replacement order"
    )

    states = [check["state"] for check in checks.values()]
    if any(state == "block" for state in states):
        eligible: Optional[bool] = False
    elif all(state == "pass" for state in states):
        eligible = True
    else:
        eligible = None

    return {
        "account_age_days": age_days,
        "checks": checks,
        "eligible": eligible,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = evaluate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {
            "error": "invalid_input",
            "detail": str(exc),
            "eligible": None,
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
