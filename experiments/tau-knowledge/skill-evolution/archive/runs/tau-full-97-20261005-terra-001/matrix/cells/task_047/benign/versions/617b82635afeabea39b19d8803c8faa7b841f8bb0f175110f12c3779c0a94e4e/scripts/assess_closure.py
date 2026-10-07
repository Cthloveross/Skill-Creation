#!/usr/bin/env python3
"""Assess mechanical portions of credit-card closure eligibility.

Input JSON schema:
{
  "now": "YYYY-MM-DD ..." | "MM/DD/YYYY ...",
  "identity_verified": true | false,
  "account": {"current_balance": "$0.00", "date_of_account_open": "YYYY-MM-DD"},
  "disputes": [{"status": "closed", "applies_to_target": true}],
  "replacement_orders": [{"status": "delivered"}]
}

The caller must establish target-account association before supplying disputes.
Output JSON always contains eligible, blockers, account_age_days, and checks.
"""

import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved", "completed", "final"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    text = value.strip()
    # Runtime timestamps may contain time zones; their leading date is sufficient.
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if match:
        return dt.date.fromisoformat(match.group(1))
    match = re.match(r"^(\d{2}/\d{2}/\d{4})", text)
    if match:
        return dt.datetime.strptime(match.group(1), "%m/%d/%Y").date()
    raise ValueError("unsupported date format")


def parse_money(value):
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if not isinstance(value, str):
        raise ValueError("balance is missing")
    cleaned = value.strip().replace("$", "").replace(",", "")
    cleaned = re.sub(r"\s*(USD|dollars?)$", "", cleaned, flags=re.I).strip()
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("balance is not numeric") from exc


def normalized_status(record):
    if not isinstance(record, dict):
        return ""
    value = record.get("status")
    return value.strip().lower() if isinstance(value, str) else ""


def main(payload):
    blockers = []
    checks = {}

    if payload.get("identity_verified") is True:
        checks["identity"] = "passed"
    else:
        checks["identity"] = "blocked"
        blockers.append("Identity verification has not been logged as complete.")

    account = payload.get("account")
    age_days = None
    if not isinstance(account, dict):
        checks["account"] = "blocked"
        checks["balance"] = "blocked"
        checks["account_age"] = "blocked"
        blockers.append("Target account data is missing.")
    else:
        checks["account"] = "provided"
        try:
            balance = parse_money(account.get("current_balance"))
            if balance == Decimal("0"):
                checks["balance"] = "passed"
            else:
                checks["balance"] = "blocked"
                blockers.append("Outstanding balance must be exactly $0.00.")
        except ValueError:
            checks["balance"] = "blocked"
            blockers.append("Target account balance is missing or unreadable.")

        try:
            today = parse_date(payload.get("now"))
            opened = parse_date(account.get("date_of_account_open"))
            age_days = (today - opened).days
            if age_days < 0:
                checks["account_age"] = "blocked"
                blockers.append("Account-open date is later than the current date.")
            elif age_days >= 60:
                checks["account_age"] = "passed"
            else:
                checks["account_age"] = "blocked"
                blockers.append("Account must be open for at least 60 days.")
        except ValueError:
            checks["account_age"] = "blocked"
            blockers.append("Current date or account-open date is missing or unreadable.")

    disputes = payload.get("disputes")
    if not isinstance(disputes, list):
        checks["disputes"] = "blocked"
        blockers.append("A completed target-account dispute assessment is required.")
    else:
        active = []
        malformed = False
        for dispute in disputes:
            if not isinstance(dispute, dict) or "applies_to_target" not in dispute:
                malformed = True
                continue
            if dispute.get("applies_to_target") is True:
                status = normalized_status(dispute)
                if status not in FINAL_DISPUTE_STATUSES:
                    active.append(status or "unknown")
        if malformed:
            checks["disputes"] = "blocked"
            blockers.append("Dispute association or status is unresolved.")
        elif active:
            checks["disputes"] = "blocked"
            blockers.append("Target account has an active, pending, or unresolved dispute.")
        else:
            checks["disputes"] = "passed"

    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        checks["replacement_orders"] = "blocked"
        blockers.append("A completed replacement-order check is required.")
    else:
        nonfinal = [normalized_status(order) or "unknown" for order in orders
                    if normalized_status(order) not in FINAL_REPLACEMENT_STATUSES]
        if nonfinal:
            checks["replacement_orders"] = "blocked"
            blockers.append("Target account has a pending or unresolved replacement-card order.")
        else:
            checks["replacement_orders"] = "passed"

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "account_age_days": age_days,
        "checks": checks,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "eligible": False,
            "blockers": ["Invalid assessment input: " + str(exc)],
            "account_age_days": None,
            "checks": {},
        }, sort_keys=True))
