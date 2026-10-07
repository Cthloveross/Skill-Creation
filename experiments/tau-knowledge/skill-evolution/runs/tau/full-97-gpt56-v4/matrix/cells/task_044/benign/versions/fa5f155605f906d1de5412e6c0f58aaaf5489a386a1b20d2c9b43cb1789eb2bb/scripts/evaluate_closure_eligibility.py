#!/usr/bin/env python3
"""Evaluate supplied credit-card closure prerequisites without performing bank actions.

Input JSON:
{
  "current_date": "YYYY-MM-DD" or ISO timestamp,
  "account_open_date": "YYYY-MM-DD" or ISO timestamp,
  "balance": "0.00" | number,
  "dispute_statuses": ["closed", ...],
  "replacement_statuses": ["delivered", ...]
}
Output JSON:
{
  "eligible": bool,
  "account_age_days": int | null,
  "checks": {"zero_balance": bool, "minimum_age": bool,
             "no_pending_disputes": bool, "no_pending_replacements": bool},
  "blockers": [string]
}
Missing or invalid required values are blockers, so callers never treat incomplete
information as eligible.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "withdrawn", "denied", "completed"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def normalized_statuses(value):
    if not isinstance(value, list):
        return None
    statuses = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None
        statuses.append(item.strip().lower().replace("-", "_").replace(" ", "_"))
    return statuses


def main(payload):
    blockers = []
    checks = {}

    try:
        balance = Decimal(str(payload.get("balance")))
        checks["zero_balance"] = balance == Decimal("0")
        if not checks["zero_balance"]:
            blockers.append("Outstanding balance must be exactly $0.00.")
    except (InvalidOperation, ValueError, TypeError):
        checks["zero_balance"] = False
        blockers.append("A valid current balance is required.")

    current = parse_date(payload.get("current_date"))
    opened = parse_date(payload.get("account_open_date"))
    age_days = None
    if current is None or opened is None or opened > current:
        checks["minimum_age"] = False
        blockers.append("Valid current and account-opening dates are required.")
    else:
        age_days = (current - opened).days
        checks["minimum_age"] = age_days >= 60
        if not checks["minimum_age"]:
            blockers.append("Account must be open for at least 60 days.")

    disputes = normalized_statuses(payload.get("dispute_statuses"))
    if disputes is None:
        checks["no_pending_disputes"] = False
        blockers.append("Complete dispute status evidence is required.")
    else:
        checks["no_pending_disputes"] = all(s in FINAL_DISPUTE_STATUSES for s in disputes)
        if not checks["no_pending_disputes"]:
            blockers.append("Active or pending disputes must be resolved before closure.")

    replacements = normalized_statuses(payload.get("replacement_statuses"))
    if replacements is None:
        checks["no_pending_replacements"] = False
        blockers.append("Complete replacement-order status evidence is required.")
    else:
        checks["no_pending_replacements"] = all(s in FINAL_REPLACEMENT_STATUSES for s in replacements)
        if not checks["no_pending_replacements"]:
            blockers.append("Pending replacement-card orders must be delivered or cancelled before closure.")

    return {
        "eligible": all(checks.values()),
        "account_age_days": age_days,
        "checks": checks,
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"eligible": False, "blockers": [f"Invalid evaluator input: {exc}"]}, separators=(",", ":")))
