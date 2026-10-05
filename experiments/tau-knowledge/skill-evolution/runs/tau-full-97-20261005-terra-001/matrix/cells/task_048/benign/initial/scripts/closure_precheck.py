#!/usr/bin/env python3
"""Evaluate supplied credit-card closure eligibility facts.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
performs no network or banking operations.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ACTIVE_DISPUTE_STATUSES = {"open", "pending", "under_review", "active", "in_review"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a YYYY-MM-DD string")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid YYYY-MM-DD date") from exc


def parse_balance(value):
    try:
        cleaned = str(value).strip().replace("$", "").replace(",", "")
        return Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("current_balance must be a decimal amount") from exc


def normalized_statuses(value, field):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{field} must be an array of strings")
    return [x.strip().lower().replace(" ", "_") for x in value]


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    opened = parse_date(payload.get("account_open_date"), "account_open_date")
    if opened > as_of:
        raise ValueError("account_open_date cannot be after as_of_date")
    balance = parse_balance(payload.get("current_balance"))
    attributable = payload.get("disputes_attributable")
    if not isinstance(attributable, bool):
        raise ValueError("disputes_attributable must be boolean")
    disputes = normalized_statuses(payload.get("dispute_statuses", []), "dispute_statuses")
    orders = normalized_statuses(
        payload.get("replacement_order_statuses", []), "replacement_order_statuses"
    )

    age_days = (as_of - opened).days
    blockers = []
    warnings = []
    checks = {
        "zero_balance": balance == Decimal("0"),
        "minimum_account_age": age_days >= 60,
        "no_pending_disputes": False,
        "no_pending_replacement_cards": all(status in FINAL_ORDER_STATUSES for status in orders),
    }
    if not checks["zero_balance"]:
        blockers.append("Outstanding balance must be exactly $0.00.")
    if not checks["minimum_account_age"]:
        blockers.append("Account must be open for at least 60 days.")
    if not attributable:
        blockers.append("Dispute records have not been confirmed as attributable to the selected account.")
    else:
        active = sorted({status for status in disputes if status in ACTIVE_DISPUTE_STATUSES})
        checks["no_pending_disputes"] = not active
        if active:
            blockers.append("Selected account has active or pending dispute status: " + ", ".join(active) + ".")
    if not checks["no_pending_replacement_cards"]:
        nonfinal = sorted({status for status in orders if status not in FINAL_ORDER_STATUSES})
        blockers.append("Selected account has non-final replacement order status: " + ", ".join(nonfinal) + ".")
    if not orders:
        warnings.append("No replacement-order statuses supplied; confirm with the live replacement-order tool immediately before closure.")

    return {
        "eligible": not blockers,
        "account_age_days": age_days,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
