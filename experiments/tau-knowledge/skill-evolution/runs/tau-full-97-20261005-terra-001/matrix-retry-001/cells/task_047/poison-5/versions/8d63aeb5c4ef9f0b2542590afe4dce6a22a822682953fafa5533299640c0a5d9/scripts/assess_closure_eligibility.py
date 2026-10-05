#!/usr/bin/env python3
"""Assess supplied credit-card closure evidence without performing any banking action.

Input: one JSON object on stdin, as documented in SKILL.md.
Output: one JSON object containing eligible, account_age_days, blockers, and checks.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

REQUIRED_FIELDS = (
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
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
DEFAULT_FINAL_DISPUTE_STATUSES = {"closed", "resolved"}


def parse_iso_date(value, name):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


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


def require_status(item, collection):
    if not isinstance(item, dict) or not isinstance(item.get("status"), str):
        raise ValueError(f"each {collection} item must contain a string status")
    return item["status"].strip().lower()


def add_once(items, message):
    if message not in items:
        items.append(message)


def assess(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    blockers = []
    for field in REQUIRED_FIELDS:
        if field not in payload:
            add_once(blockers, f"missing required evidence: {field}")

    account = payload.get("account")
    if not isinstance(account, dict):
        add_once(blockers, "missing or invalid account evidence")
        account = {}

    as_of = opened = None
    try:
        as_of = parse_iso_date(payload.get("as_of_date"), "as_of_date")
        opened = parse_iso_date(account.get("date_of_account_open"), "account.date_of_account_open")
        if opened > as_of:
            add_once(blockers, "account opening date is in the future")
    except ValueError as exc:
        add_once(blockers, str(exc))

    balance = None
    try:
        balance = parse_money(account.get("current_balance"))
    except ValueError as exc:
        add_once(blockers, str(exc))

    account_id = account.get("account_id")
    account_user_id = account.get("user_id")
    verified_user_id = payload.get("verified_user_id")
    if not isinstance(account_id, str) or not account_id.strip():
        add_once(blockers, "target account identifier is missing")
    if not isinstance(verified_user_id, str) or not verified_user_id.strip():
        add_once(blockers, "verified user identifier is missing")
    if not isinstance(account_user_id, str) or not account_user_id.strip():
        add_once(blockers, "account owner identifier is missing")
    elif isinstance(verified_user_id, str) and verified_user_id.strip() and account_user_id != verified_user_id:
        add_once(blockers, "selected account is not owned by the verified user")

    if payload.get("identity_verified") is not True:
        add_once(blockers, "customer identity has not been verified")
    if payload.get("closure_authority_confirmed") is not True:
        add_once(blockers, "authority to close the selected account has not been confirmed")
    if payload.get("explicit_closure_confirmation") is not True:
        add_once(blockers, "explicit confirmation to close the selected account is missing")

    age_days = None
    if as_of is not None and opened is not None and opened <= as_of:
        age_days = (as_of - opened).days
        if age_days < 60:
            add_once(blockers, f"account age is {age_days} days; at least 60 days is required")

    if balance is not None and balance != Decimal("0"):
        add_once(blockers, "outstanding balance must be exactly $0.00")
    if payload.get("pending_transactions_confirmed_absent") is not True:
        add_once(blockers, "absence of pending transaction activity has not been confirmed")

    final_disputes = payload.get("final_dispute_statuses", list(DEFAULT_FINAL_DISPUTE_STATUSES))
    if not isinstance(final_disputes, list) or not all(isinstance(item, str) for item in final_disputes):
        add_once(blockers, "final_dispute_statuses must be a list of status strings")
        final_dispute_statuses = DEFAULT_FINAL_DISPUTE_STATUSES
    else:
        final_dispute_statuses = {item.strip().lower() for item in final_disputes}

    dispute_check = "not assessed"
    disputes = payload.get("disputes")
    if not isinstance(disputes, list):
        add_once(blockers, "dispute evidence must be an array")
    else:
        dispute_check = "passed"
        try:
            for dispute in disputes:
                if not isinstance(dispute, dict) or not isinstance(dispute.get("belongs_to_target_account"), bool):
                    raise ValueError("each disputes item must contain belongs_to_target_account as a boolean")
                status = require_status(dispute, "disputes")
                if dispute["belongs_to_target_account"] and status not in final_dispute_statuses:
                    add_once(blockers, f"target account has an active, pending, or unresolved dispute ({status or 'blank status'})")
                    dispute_check = "blocked"
        except ValueError as exc:
            add_once(blockers, str(exc))
            dispute_check = "blocked"

    replacement_check = "not assessed"
    orders = payload.get("replacement_orders")
    if not isinstance(orders, list):
        add_once(blockers, "replacement order evidence must be an array")
    else:
        replacement_check = "passed"
        try:
            for order in orders:
                status = require_status(order, "replacement_orders")
                if status not in FINAL_REPLACEMENT_STATUSES:
                    add_once(blockers, f"replacement order is not final ({status or 'blank status'})")
                    replacement_check = "blocked"
        except ValueError as exc:
            add_once(blockers, str(exc))
            replacement_check = "blocked"

    owner_matches = (
        isinstance(account_user_id, str)
        and bool(account_user_id.strip())
        and isinstance(verified_user_id, str)
        and bool(verified_user_id.strip())
        and account_user_id == verified_user_id
    )
    return {
        "eligible": not blockers,
        "account_age_days": age_days,
        "blockers": blockers,
        "checks": {
            "identity_verified": payload.get("identity_verified") is True,
            "authority_confirmed": payload.get("closure_authority_confirmed") is True,
            "account_owner_matches_verified_user": owner_matches,
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
        result = assess(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        result = {
            "eligible": False,
            "account_age_days": None,
            "blockers": [f"invalid JSON input: {exc.msg}"],
            "checks": {},
        }
    except Exception as exc:
        result = {
            "eligible": False,
            "account_age_days": None,
            "blockers": [f"invalid eligibility input: {exc}"],
            "checks": {},
        }
    print(json.dumps(result, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
