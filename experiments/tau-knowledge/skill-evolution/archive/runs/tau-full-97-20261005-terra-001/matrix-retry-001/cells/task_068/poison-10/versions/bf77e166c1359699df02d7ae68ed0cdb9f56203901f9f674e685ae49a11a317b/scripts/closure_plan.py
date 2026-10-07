#!/usr/bin/env python3
"""Assess documented personal-checking closure prerequisites from JSON input."""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

TIERS = {
    "Light Blue Account": (15, 30, 0),
    "Light Green Account": (15, 30, 0),
    "Green Fee-Free Account": (15, 30, 0),
    "Blue Account": (25, 60, 3),
    "Green Account (checking)": (25, 60, 3),
    "Evergreen Account": (50, 90, 7),
    "Bluest Account": (100, 180, 14),
}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def money(value, field):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal USD amount") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount.quantize(Decimal("0.01"))


def main(payload):
    required = ["account_class", "status", "balance", "date_opened", "current_date",
                "pending_transaction_count", "all_associated_cards_closed"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

    account_class = payload["account_class"]
    if account_class not in TIERS:
        raise ValueError("unsupported account_class for personal checking closure")
    fee_amount, fee_window_days, notice_days = TIERS[account_class]
    opened = parse_date(payload["date_opened"], "date_opened")
    today = parse_date(payload["current_date"], "current_date")
    if opened > today:
        raise ValueError("date_opened cannot be after current_date")
    balance = money(payload["balance"], "balance")
    try:
        pending_count = int(payload["pending_transaction_count"])
    except (TypeError, ValueError) as exc:
        raise ValueError("pending_transaction_count must be a nonnegative integer") from exc
    if pending_count < 0:
        raise ValueError("pending_transaction_count must be a nonnegative integer")

    age_days = (today - opened).days
    # "within N days" includes the Nth calendar day after opening.
    early_fee_applies = age_days <= fee_window_days
    fee = Decimal(fee_amount if early_fee_applies else 0)
    blockers = []
    if payload["status"] != "OPEN":
        blockers.append("account status must be OPEN")
    if pending_count != 0:
        blockers.append("account has pending transactions")
    if payload["all_associated_cards_closed"] is not True:
        blockers.append("all associated debit cards must be closed first")
    if early_fee_applies:
        if balance < fee:
            blockers.append(f"balance must be at least ${fee:.2f} for the early closure fee")
    elif balance != Decimal("0.00"):
        blockers.append("balance must be exactly $0.00 when no early closure fee applies")

    notice_complete_on = today
    notice_satisfied = notice_days == 0
    if notice_days:
        notice_value = payload.get("notice_request_date")
        if notice_value is None:
            blockers.append(f"a {notice_days}-day closure notice request date is required")
        else:
            requested = parse_date(notice_value, "notice_request_date")
            if requested > today:
                blockers.append("notice_request_date cannot be after current_date")
            else:
                notice_complete_on = requested + timedelta(days=notice_days)
                notice_satisfied = today >= notice_complete_on
                if not notice_satisfied:
                    blockers.append(f"required closure notice completes on {notice_complete_on.isoformat()}")

    return {
        "account_class": account_class,
        "account_age_days": age_days,
        "early_closure_fee_applies": early_fee_applies,
        "early_closure_fee": f"{fee:.2f}",
        "notice_period_days": notice_days,
        "notice_complete_on": notice_complete_on.isoformat(),
        "notice_satisfied": notice_satisfied,
        "blockers": blockers,
        "can_invoke_close_tool": not blockers,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
