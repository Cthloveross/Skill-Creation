#!/usr/bin/env python3
"""Evaluate normalized facts for a credit-card account closure workflow.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never contacts banking systems and is deliberately conservative when information
is unavailable or malformed.
"""

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ALLOWED_REASONS = {
    "annual_fee",
    "not_using_card",
    "found_better_card",
    "unhappy_with_rewards",
    "simplifying_finances",
    "negative_experience",
    "other",
}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
BLOCKING_DISPUTE_STATUSES = {
    "active", "pending", "open", "under_review", "under review",
    "in_review", "in review",
}


def parse_date(value):
    """Return a date from common tool date formats, or None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    candidates = (value[:10], value)
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def parse_money(value):
    """Return a Decimal from a currency string/number, or None."""
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalized_status(record):
    if not isinstance(record, dict):
        return None
    value = record.get("status")
    return value.strip().lower() if isinstance(value, str) else None


def main(state):
    account = state.get("account") if isinstance(state.get("account"), dict) else {}
    current = parse_date(state.get("current_date"))
    opened = parse_date(account.get("date_of_account_open"))
    balance = parse_money(account.get("current_balance"))

    blockers = []
    next_actions = []
    details = {
        "account_age_days": None,
        "balance_is_zero": None,
        "dispute_check": "not_checked",
        "replacement_check": "not_checked",
        "history_check": "not_checked",
    }

    if not state.get("identity_logged", False):
        blockers.append("identity verification has not been successfully logged")
        next_actions.append("verify_two_identity_fields_and_log_verification")

    if not account.get("account_id"):
        blockers.append("credit_card_account_id is missing")
        next_actions.append("identify_requested_account")

    if current is None or opened is None:
        blockers.append("current date or account-open date is unavailable or invalid")
        next_actions.append("obtain_valid_current_date_and_account_open_date")
    else:
        age_days = (current - opened).days
        details["account_age_days"] = age_days
        if age_days < 60:
            blockers.append("account has been open fewer than 60 days")
        elif age_days < 0:
            blockers.append("account-open date is after the current date")

    if balance is None:
        blockers.append("current balance is unavailable or invalid")
        next_actions.append("obtain_current_account_balance")
    else:
        details["balance_is_zero"] = balance == Decimal("0")
        if balance != Decimal("0"):
            blockers.append("outstanding balance is not zero")

    disputes = state.get("disputes")
    if disputes is None:
        blockers.append("dispute history has not been checked")
        next_actions.append("call_get_user_dispute_history_7291")
    elif not isinstance(disputes, list):
        blockers.append("dispute history result is malformed or ambiguous")
    else:
        statuses = [normalized_status(item) for item in disputes]
        if any(status is None for status in statuses):
            blockers.append("at least one dispute has an unclear status")
            details["dispute_check"] = "ambiguous"
        elif any(status in BLOCKING_DISPUTE_STATUSES for status in statuses):
            blockers.append("active or pending dispute exists")
            details["dispute_check"] = "blocked"
        else:
            details["dispute_check"] = "clear"

    orders = state.get("replacement_orders")
    if orders is None:
        blockers.append("pending replacement orders have not been checked")
        next_actions.append("call_get_pending_replacement_orders_5765")
    elif not isinstance(orders, list):
        blockers.append("replacement-order result is malformed or ambiguous")
    else:
        statuses = [normalized_status(item) for item in orders]
        if any(status is None for status in statuses):
            blockers.append("at least one replacement order has an unclear status")
            details["replacement_check"] = "ambiguous"
        elif any(status not in FINAL_REPLACEMENT_STATUSES for status in statuses):
            blockers.append("a pending or non-final replacement-card order exists")
            details["replacement_check"] = "blocked"
        else:
            details["replacement_check"] = "clear"

    eligibility_blockers = list(blockers)
    if eligibility_blockers:
        return {
            "ready_to_close": False,
            "blockers": blockers,
            "next_actions": list(dict.fromkeys(next_actions)),
            "details": details,
        }

    history = state.get("recent_closure_record")
    if history is None:
        details["history_check"] = "not_checked"
        return {
            "ready_to_close": False,
            "blockers": ["closure-reason history for the past year has not been checked"],
            "next_actions": ["call_get_closure_reason_history_8293"],
            "details": details,
        }

    if history is True:
        details["history_check"] = "recent_record_found"
        return {
            "ready_to_close": True,
            "blockers": [],
            "next_actions": ["call_close_credit_card_account_7834"],
            "details": details,
        }

    if history is not False:
        details["history_check"] = "ambiguous"
        return {
            "ready_to_close": False,
            "blockers": ["closure-reason history result is ambiguous"],
            "next_actions": ["retry_or_clarify_closure_reason_history"],
            "details": details,
        }

    details["history_check"] = "no_recent_record"
    reason = state.get("closure_reason")
    if reason not in ALLOWED_REASONS:
        return {
            "ready_to_close": False,
            "blockers": ["a permitted closure reason has not been established"],
            "next_actions": ["obtain_and_normalize_closure_reason"],
            "details": details,
        }

    if not state.get("reason_logged", False):
        return {
            "ready_to_close": False,
            "blockers": ["closure reason has not been logged"],
            "next_actions": ["call_log_credit_card_closure_reason_4521"],
            "details": details,
        }

    retention = state.get("retention") if isinstance(state.get("retention"), dict) else {}
    offered = retention.get("offered", False)
    declined = retention.get("declined", False)
    if not offered:
        return {
            "ready_to_close": False,
            "blockers": ["required retention offer has not been made"],
            "next_actions": ["address_reason_and_make_one_tier_appropriate_retention_offer"],
            "details": details,
        }
    if not declined:
        return {
            "ready_to_close": False,
            "blockers": ["customer decision on the retention offer is not recorded as declined"],
            "next_actions": ["obtain_customer_retention_offer_decision"],
            "details": details,
        }

    return {
        "ready_to_close": True,
        "blockers": [],
        "next_actions": ["call_close_credit_card_account_7834"],
        "details": details,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({
            "ready_to_close": False,
            "blockers": ["invalid evaluator input: " + str(exc)],
            "next_actions": ["correct_normalized_closure_state"],
            "details": {},
        }, sort_keys=True))
