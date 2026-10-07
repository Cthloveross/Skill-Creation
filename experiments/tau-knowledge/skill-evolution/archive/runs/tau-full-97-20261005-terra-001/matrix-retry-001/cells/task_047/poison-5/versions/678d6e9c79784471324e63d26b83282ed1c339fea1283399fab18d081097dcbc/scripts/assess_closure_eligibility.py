#!/usr/bin/env python3
"""Deterministically assess supplied credit-card closure eligibility evidence.

Reads one JSON object on stdin and emits one JSON object on stdout. This helper does
not access tools and does not make any account change.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


REQUIRED_TOP_LEVEL = (
    "as_of_date",
    "identity_verified",
    "closure_authority_confirmed",
    "explicit_closure_confirmation",
    "verified_user_id",
    "account",
    "pending_transactions_confirmed_absent",
    "disputes",
    "replacement_orders",
)


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD") from exc


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("current_balance must be a number or currency string")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        text = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError("current_balance must be a number or currency string")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("current_balance is not a valid amount") from exc


def status_text(item, collection_name):
    if not isinstance(item, dict) or not isinstance(item.get("status"), str):
        raise ValueError(f"each {collection_name} item must contain a string status")
    return item["status"].strip().lower()


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    blockers = []
    for field in REQUIRED_TOP_LEVEL:
        if field not in payload:
            blockers.append(f"missing required evidence: {field}")

    account = payload.get("account")
    if not isinstance(account, dict):
        blockers.append("missing or invalid account evidence")
        account = {}

    as_of = None
    opened = None
    balance = None
    try:
        as_of = parse_date(payload.get("as_of_date"), "as_of_date")
        opened = parse_date(account.get("date_of_account_open"), "account.date_of_account_open")
        if opened > as_of:
            blockers.append("account opening date is in the future")
    except ValueError as exc:
        blockers.append(str(exc))

    try:
        balance = parse_money(account.get("current_balance"))
    except ValueError as exc:
        blockers.append(str(exc))

    account_id = account.get("account_id")
    account_user_id = account.get("user_id")
    verified_user_id = payload.get("verified_user_id")
    if not isinstance(account_id, str) or not account_id.strip():
        blockers.append("target account identifier is missing")
    if not isinstance(verified_user_id, str) or not verified_user_id.strip():
        blockers.append("verified user identifier is missing")
    if not isinstance(account_user_id, str) or not account_user_id.strip():
        blockers.append("account owner identifier is missing")
    elif isinstance(verified_user_id, str) and verified_user_id.strip() and account_user_id != verified_user_id:
        blockers.append("selected account is not owned by the verified user")

    if payload.get("identity_verified") is not True:
        blockers.append("customer identity has not been verified")
    if payload.get("closure_authority_confirmed") is not True:
        blockers.append("authority to close the selected account has not been confirmed")
    if payload.get("explicit_closure_confirmation") is not True:
        blockers.append("explicit confirmation to close the selected account is missing")

    age_days = None
    if as_of is not None and opened is not None and opened <= as_of:
        age_days = (as_of - opened).days
        if age_days < 60:
            blockers.append(f"account age is {age_days} days; at least 60 days is required")

    if balance is not None and balance != Decimal("0"):
        blockers.append("outstanding balance must be exactly $0.00")
    if payload.get("pending_transactions_confirmed_absent") is not True:
        blockers.append("absence of pending transaction activity has not been confirmed")

    final_disputes = payload.get("final_dispute_statuses", ["closed", "resolved"])
    if not isinstance(final_disputes, list) or not all(isinstance(x, str) for x in final_disputes):
        blockers.append("final_dispute_statuses must be a list of status strings")
        final_disputes = ["closed", "resolved"]
    final_disputes = {value.strip().lower() for value in final_disputes}

    disputes = payload.get("disputes")
    dispute_check = "not assessed"
    if isinstance(disputes, list):
        dispute_check = "passed"
        try:
            for dispute in disputes:
                if not isinstance(dispute, dict) or not isinstance(dispute.get("belongs_to_target_account"), bool):
                    raise ValueError("each disputes item must contain belongs_to_target_account as a boolean")
                status = status_text(dispute, "disputes")
                if dispute["belongs_to_target_account"] and status not in final_disputes:
                    blockers.append(f"target account has an active, pending, or unresolved dispute ({status or 'blank status'})")
                    dispute_check = "blocked"
        except ValueError as exc:
            blockers.append(str(exc))
            dispute_check = "blocked"
    else:
        blockers.append("dispute evidence must be an array")

    final_orders = {"delivered", "cancelled"}
    orders = payload.get("replacement_orders")
    replacement_check = "not assessed"
    if isinstance(orders, list):
        replacement_check = "passed"
        try:
            for order in orders:
                status = status_text(order, "replacement_orders")
                if status not in final_orders:
                    blockers.append(f"replacement order is not final ({status or 'blank status'})")
                    replacement_check = "blocked"
        except ValueError as exc:
            blockers.append(str(exc))
            replacement_check = "blocked"
    else:
        blockers.append("replacement order evidence must be an array")

    # Preserve order while removing repeated messages caused by multiple bad records.
    unique_blockers = list(dict.fromkeys(blockers))
    return {
        "eligible": not unique_blockers,
        "account_age_days": age_days,
        "blockers": unique_blockers,
        "checks": {
            "identity_verified": payload.get("identity_verified") is True,
            "authority_confirmed": payload.get("closure_authority_confirmed") is True,
            "account_owner_matches_verified_user": (
                isinstance(account_user_id, str)
                and isinstance(verified_user_id, str)
                and bool(account_user_id)
                and account_user_id == verified_user_id
            ),
            "explicit_closure_confirmation": payload.get("explicit_closure_confirmation") is True,
            "minimum_account_age_met": age_days is not None and age_days >= 60,
            "zero_balance": balance == Decimal("0") if balance is not None else False,
            "pending_transactions_absent": payload.get("pending_transactions_confirmed_absent") is True,
            "disputes": dispute_check,
            "replacement_orders": replacement_check,
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
        result = assess(payload)
    except json.JSONDecodeError as exc:
        result = {
            "eligible": False,
            "account_age_days": None,
            "blockers": [f"invalid JSON input: {exc.msg}"],
            "checks": {},
        }
    except Exception as exc:  # Return a usable validation result, never an approval.
        result = {
            "eligible": False,
            "account_age_days": None,
            "blockers": [f"invalid eligibility input: {exc}"],
            "checks": {},
        }
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
