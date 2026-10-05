#!/usr/bin/env python3
"""Compute credit-card closure preflight status from normalized runtime data.

Input JSON object:
  account_open_date: str, YYYY-MM-DD, MM/DD/YYYY, or timestamp starting with it
  as_of: str, same date formats (normally current date/time)
  current_balance: str | int | float | Decimal-compatible value
  disputes: list[object], each normally has a status field
  replacement_orders: list[object], each normally has a status field

Output JSON object:
  eligible: true, false, or null (null means evidence was invalid/incomplete)
  blockers: [{code: str, message: str}]
  errors: [str]
  checks: object with normalized per-check outcomes
  account_age_days: int or null
  annual_fee_waiver_expiration: MM/DD/YYYY or null

A dispute passes only when each supplied dispute has status closed/resolved.
A replacement order passes only when every supplied order is delivered/cancelled.
Unknown statuses deliberately block rather than approving a closure.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

FINAL_DISPUTE_STATUSES = {"closed", "resolved"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value: Any) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty string")
    candidate = value.strip()
    # Tool timestamps in this environment begin with the calendar date.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(candidate[:10], fmt).date()
        except ValueError:
            pass
    # Permit a date-only US value even when slicing at 10 included extra text.
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format")


def parse_balance(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("balance is missing or invalid")
    text = str(value).strip().replace(",", "")
    text = re.sub(r"^\$", "", text)
    # Parentheses are a conventional negative amount representation.
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("balance is not decimal-compatible") from exc


def status_of(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    status = record.get("status")
    if not isinstance(status, str) or not status.strip():
        return None
    return status.strip().lower().replace(" ", "_")


def one_year_later(day: date) -> date:
    try:
        return day.replace(year=day.year + 1)
    except ValueError:
        # The only normal replacement failure is February 29 in a non-leap year.
        return day.replace(year=day.year + 1, month=2, day=28)


def main(payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    blockers: list[dict[str, str]] = []
    checks: dict[str, Any] = {}
    account_age_days: int | None = None
    waiver_expiration: str | None = None

    try:
        opened = parse_date(payload.get("account_open_date"))
        as_of = parse_date(payload.get("as_of"))
        if opened > as_of:
            raise ValueError("account_open_date is after as_of")
        account_age_days = (as_of - opened).days
        checks["account_age"] = {"passed": account_age_days >= 60, "days": account_age_days}
        waiver_expiration = one_year_later(as_of).strftime("%m/%d/%Y")
        if account_age_days < 60:
            blockers.append({"code": "account_too_new", "message": "Account must be open for at least 60 days."})
    except ValueError as exc:
        errors.append(f"account age could not be determined: {exc}")
        checks["account_age"] = {"passed": None}

    try:
        balance = parse_balance(payload.get("current_balance"))
        balance_passed = balance == Decimal("0")
        checks["zero_balance"] = {"passed": balance_passed, "balance": str(balance)}
        if not balance_passed:
            blockers.append({"code": "nonzero_balance", "message": "Outstanding balance must be exactly $0.00."})
    except ValueError as exc:
        errors.append(f"balance could not be determined: {exc}")
        checks["zero_balance"] = {"passed": None}

    disputes = payload.get("disputes")
    if not isinstance(disputes, list):
        errors.append("disputes must be an array")
        checks["no_pending_disputes"] = {"passed": None}
    else:
        unresolved = []
        for item in disputes:
            status = status_of(item)
            if status not in FINAL_DISPUTE_STATUSES:
                unresolved.append(status if status is not None else "missing_or_unknown")
        dispute_passed = not unresolved
        checks["no_pending_disputes"] = {"passed": dispute_passed, "unresolved_statuses": unresolved}
        if not dispute_passed:
            blockers.append({"code": "pending_or_ambiguous_dispute", "message": "All transaction disputes must be resolved before closure."})

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        errors.append("replacement_orders must be an array")
        checks["no_pending_replacement_cards"] = {"passed": None}
    else:
        nonfinal = []
        for item in orders:
            status = status_of(item)
            if status not in FINAL_REPLACEMENT_STATUSES:
                nonfinal.append(status if status is not None else "missing_or_unknown")
        replacement_passed = not nonfinal
        checks["no_pending_replacement_cards"] = {"passed": replacement_passed, "nonfinal_statuses": nonfinal}
        if not replacement_passed:
            blockers.append({"code": "pending_replacement_card", "message": "Replacement-card orders must be delivered or cancelled before closure."})

    eligible: bool | None
    if errors:
        eligible = None
    else:
        eligible = not blockers

    return {
        "eligible": eligible,
        "blockers": blockers,
        "errors": errors,
        "checks": checks,
        "account_age_days": account_age_days,
        "annual_fee_waiver_expiration": waiver_expiration,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "eligible": None,
            "blockers": [],
            "errors": [f"invalid input: {exc}"],
            "checks": {},
            "account_age_days": None,
            "annual_fee_waiver_expiration": None,
        }, sort_keys=True))
