#!/usr/bin/env python3
"""Evaluate supplied credit-card closure eligibility facts.

Reads one JSON object from stdin and emits one JSON object to stdout.  This helper
is deliberately side-effect free and does not treat missing status information as
approval.
"""

import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


DATE_PATTERNS = (
    (re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{2}/\d{2}/\d{4})\b"), "%m/%d/%Y"),
)


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for pattern, layout in DATE_PATTERNS:
        match = pattern.search(value)
        if match:
            return datetime.strptime(match.group(1), layout).date()
    raise ValueError("date must contain YYYY-MM-DD or MM/DD/YYYY")


def parse_money(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("current_balance is required")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError("current_balance must be numeric or a currency string")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid amount") from exc


def parse_points(value):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("reward_points must be an integer")
    try:
        points = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("reward_points must be an integer") from exc
    if points < 0:
        raise ValueError("reward_points cannot be negative")
    return points


def as_money(value):
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def evaluate(payload):
    account = payload.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")

    account_id = account.get("account_id")
    now = parse_date(payload.get("now"))
    opened = parse_date(account.get("date_of_account_open"))
    balance = parse_money(account.get("current_balance"))
    points = parse_points(account.get("reward_points"))

    blockers = []
    unknowns = []

    expected_user_id = payload.get("expected_user_id")
    account_user_id = account.get("user_id")
    if expected_user_id is not None:
        if not isinstance(account_user_id, str) or not account_user_id:
            unknowns.append("account_ownership")
        elif account_user_id != expected_user_id:
            blockers.append("account_not_owned_by_verified_user")

    # Balance is evaluated first because a nonzero balance must stop the process
    # before retention discussion.
    if balance != Decimal("0"):
        blockers.append("outstanding_balance_must_be_zero")

    dispute_status = payload.get("pending_disputes")
    if dispute_status is True:
        blockers.append("pending_dispute")
    elif dispute_status is not False:
        unknowns.append("pending_disputes")

    replacement_status = payload.get("pending_replacement_cards")
    if replacement_status is True:
        blockers.append("pending_replacement_card")
    elif replacement_status is not False:
        unknowns.append("pending_replacement_cards")

    age_days = (now - opened).days
    earliest = opened + timedelta(days=60)
    if age_days < 0:
        blockers.append("account_open_date_in_future")
    elif age_days < 60:
        blockers.append("account_less_than_60_days_old")

    deadline = None
    request_date = payload.get("closure_request_date")
    if request_date is not None:
        deadline = (parse_date(request_date) + timedelta(days=45)).isoformat()

    reward_value = None
    if points is not None:
        reward_value = as_money(Decimal(points) * Decimal("0.01"))

    return {
        "ok": True,
        "account_id": account_id if isinstance(account_id, str) else None,
        "age_days": age_days,
        "earliest_eligible_date": earliest.isoformat(),
        "balance": as_money(balance),
        "reward_points": points,
        "reward_credit_value": reward_value,
        "closure_eligible": not blockers and not unknowns,
        "blockers": blockers,
        "unknowns": unknowns,
        "rewards_redemption_deadline": deadline,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = evaluate(payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
