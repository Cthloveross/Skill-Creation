#!/usr/bin/env python3
"""Fail-closed preflight assessment for a credit-card account closure.

Reads one JSON object from stdin and writes one JSON object to stdout.  This is a
pure validator: it does not retrieve data, invoke tools, or modify accounts.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DISPUTE_STATES = {"none", "active_for_account", "active_other_account", "ambiguous", "unknown"}
HISTORY_STATES = {"checked_prior_record", "checked_no_record", "unknown"}
OFFER_STATES = {"not_needed_prior_record", "not_made", "offered_declined", "accepted", "unknown"}
FINAL_ORDER_STATUSES = {"delivered", "cancelled"}


def parse_day(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty date string")
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must begin with YYYY-MM-DD") from exc


def parse_balance(value):
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        raise ValueError("account.balance must be a decimal or currency string")
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("account.balance is not a valid decimal") from exc


def require_bool(data, key):
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")

    today = parse_day(data.get("today"), "today")
    account = data.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    opened = parse_day(account.get("opened_on"), "account.opened_on")
    balance = parse_balance(account.get("balance"))
    if opened > today:
        raise ValueError("account.opened_on cannot be after today")

    dispute_state = data.get("dispute_state")
    history_state = data.get("history_state")
    offer_state = data.get("offer_state")
    if dispute_state not in DISPUTE_STATES:
        raise ValueError("dispute_state is invalid")
    if history_state not in HISTORY_STATES:
        raise ValueError("history_state is invalid")
    if offer_state not in OFFER_STATES:
        raise ValueError("offer_state is invalid")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        raise ValueError("replacement_orders must be an array")
    nonfinal_orders = []
    for index, order in enumerate(orders):
        if not isinstance(order, dict) or not isinstance(order.get("status"), str):
            raise ValueError(f"replacement_orders[{index}].status must be a string")
        status = order["status"].strip().lower()
        if status not in FINAL_ORDER_STATUSES:
            nonfinal_orders.append(status or "missing")

    identity_logged = require_bool(data, "identity_verified_logged")
    replacement_fresh = require_bool(data, "replacement_check_fresh")
    reason_logged = require_bool(data, "reason_logged")
    still_requested = require_bool(data, "customer_still_requests_closure")

    blockers = []
    age_days = (today - opened).days
    if not identity_logged:
        blockers.append("identity_verification_not_logged")
    if dispute_state == "active_for_account":
        blockers.append("pending_dispute_on_requested_account")
    elif dispute_state in {"ambiguous", "unknown"}:
        blockers.append("dispute_status_unresolved")
    if balance != Decimal("0"):
        blockers.append("nonzero_outstanding_balance")
    if age_days < 60:
        blockers.append("account_under_60_days_old")
    if nonfinal_orders:
        blockers.append("pending_replacement_order")
    if not replacement_fresh:
        blockers.append("replacement_check_not_fresh")

    eligibility_blockers = {
        "pending_dispute_on_requested_account",
        "dispute_status_unresolved",
        "nonzero_outstanding_balance",
        "account_under_60_days_old",
        "pending_replacement_order",
        "replacement_check_not_fresh",
    }
    eligible = not any(item in eligibility_blockers for item in blockers)

    retention_complete = False
    if history_state == "unknown":
        blockers.append("closure_reason_history_not_checked")
    elif history_state == "checked_prior_record":
        if offer_state != "not_needed_prior_record":
            blockers.append("retention_state_inconsistent_with_prior_history")
        else:
            retention_complete = True
    else:  # checked_no_record
        if not reason_logged:
            blockers.append("closure_reason_not_logged")
        if offer_state == "offered_declined" and reason_logged:
            retention_complete = True
        elif offer_state == "accepted":
            blockers.append("customer_accepted_retention_solution")
        else:
            blockers.append("single_retention_offer_not_declined")

    if not still_requested:
        blockers.append("customer_has_not_confirmed_current_closure_request")

    ready = eligible and identity_logged and retention_complete and still_requested and not blockers
    return {
        "account_age_days": age_days,
        "balance_is_zero": balance == Decimal("0"),
        "nonfinal_replacement_statuses": nonfinal_orders,
        "eligible": eligible,
        "retention_complete": retention_complete,
        "ready_to_close": ready,
        "blockers": blockers,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"ready_to_close": False, "error": str(error)}, separators=(",", ":")))
        sys.exit(2)
