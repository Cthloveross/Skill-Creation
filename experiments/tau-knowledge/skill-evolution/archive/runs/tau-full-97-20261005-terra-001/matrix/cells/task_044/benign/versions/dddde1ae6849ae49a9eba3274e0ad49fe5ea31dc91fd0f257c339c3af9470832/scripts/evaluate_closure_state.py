#!/usr/bin/env python3
"""Conservatively evaluate normalized facts for a credit-card closure workflow.

Read one JSON object on stdin and emit one JSON object on stdout. This helper has
no banking-system access and does not authorize closure.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
FINAL_ORDERS = {"delivered", "cancelled", "canceled"}
BLOCKING_DISPUTES = {
    "active", "pending", "open", "under_review", "under review", "in_review", "in review"
}
TIERS = {"entry", "mid", "premium"}


def date_value(value):
    if not isinstance(value, str):
        return None
    for candidate in (value[:10], value.strip()):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    return None


def money_value(value):
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if not cleaned or cleaned in {"-", ".", "-."}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def status(item):
    value = item.get("status") if isinstance(item, dict) else None
    return value.strip().lower() if isinstance(value, str) else None


def result(ready, blockers, actions, details):
    return {
        "ready_to_close": ready,
        "blockers": blockers,
        "next_actions": list(dict.fromkeys(actions)),
        "details": details,
    }


def evaluate(state):
    account = state.get("account") if isinstance(state.get("account"), dict) else {}
    blockers, actions = [], []
    details = {
        "account_age_days": None, "balance_is_zero": None,
        "dispute_check": "not_checked", "replacement_check": "not_checked",
        "history_check": "not_checked", "required_retention_tier": None,
    }

    if state.get("identity_logged") is not True:
        blockers.append("identity verification has not been successfully logged")
        actions.append("verify_two_identity_fields_and_log_verification")
    if not account.get("account_id"):
        blockers.append("credit_card_account_id is missing")
        actions.append("identify_requested_account")

    today, opened = date_value(state.get("current_date")), date_value(account.get("date_of_account_open"))
    if today is None or opened is None:
        blockers.append("current date or account-open date is unavailable or invalid")
        actions.append("obtain_valid_current_date_and_account_open_date")
    else:
        age = (today - opened).days
        details["account_age_days"] = age
        if age < 0:
            blockers.append("account-open date is after the current date")
        elif age < 60:
            blockers.append("account has been open fewer than 60 days")

    balance = money_value(account.get("current_balance"))
    if balance is None:
        blockers.append("current balance is unavailable or invalid")
        actions.append("obtain_current_account_balance")
    else:
        details["balance_is_zero"] = balance == 0
        if balance != 0:
            blockers.append("outstanding balance is not zero")

    disputes = state.get("disputes")
    if disputes is None:
        blockers.append("dispute history has not been checked")
        actions.append("call_get_user_dispute_history_7291")
    elif not isinstance(disputes, list):
        blockers.append("dispute history result is malformed or ambiguous")
    else:
        values = [status(x) for x in disputes]
        if any(x is None for x in values):
            blockers.append("at least one dispute has an unclear status")
            details["dispute_check"] = "ambiguous"
        elif any(x in BLOCKING_DISPUTES for x in values):
            blockers.append("active or pending dispute exists")
            details["dispute_check"] = "blocked"
        else:
            details["dispute_check"] = "clear"

    orders = state.get("replacement_orders")
    if orders is None:
        blockers.append("pending replacement orders have not been checked")
        actions.append("call_get_pending_replacement_orders_5765")
    elif not isinstance(orders, list):
        blockers.append("replacement-order result is malformed or ambiguous")
    else:
        values = [status(x) for x in orders]
        if any(x is None for x in values):
            blockers.append("at least one replacement order has an unclear status")
            details["replacement_check"] = "ambiguous"
        elif any(x not in FINAL_ORDERS for x in values):
            blockers.append("a pending or non-final replacement-card order exists")
            details["replacement_check"] = "blocked"
        else:
            details["replacement_check"] = "clear"

    if blockers:
        return result(False, blockers, actions, details)

    history = state.get("recent_closure_record")
    if history is None:
        return result(False, ["closure-reason history for the past year has not been checked"],
                      ["call_get_closure_reason_history_8293"], details)
    if history is True:
        details["history_check"] = "recent_record_found"
        return result(True, [], ["call_close_credit_card_account_7834"], details)
    if history is not False:
        details["history_check"] = "ambiguous"
        return result(False, ["closure-reason history result is ambiguous"],
                      ["retry_or_clarify_closure_reason_history"], details)
    details["history_check"] = "no_recent_record"

    reason = state.get("closure_reason")
    if reason not in REASONS:
        return result(False, ["a permitted closure reason has not been established"],
                      ["obtain_and_normalize_closure_reason"], details)
    if state.get("reason_logged") is not True:
        return result(False, ["closure reason has not been logged"],
                      ["call_log_credit_card_closure_reason_4521"], details)

    retention = state.get("retention") if isinstance(state.get("retention"), dict) else {}
    if reason == "found_better_card" and retention.get("concern_addressed") is not True:
        return result(False, ["better-card features have not been addressed before retention"],
                      ["ask_which_features_attracted_customer_and_offer_supported_comparable_product"], details)

    tier = retention.get("tier")
    card_type = account.get("card_type")
    if card_type == "Gold Rewards Card" and tier != "premium":
        return result(False, ["Gold Rewards Card requires the premium retention tier"],
                      ["set_retention_tier_to_premium_and_offer_5000_points_or_50_statement_credit"], details)
    if tier not in TIERS:
        return result(False, ["retention card tier is unknown"],
                      ["determine_authoritative_retention_card_tier"], details)
    details["required_retention_tier"] = tier

    if retention.get("offered") is not True:
        amounts = {
            "entry": "500 bonus points or a $5 statement credit",
            "mid": "2,000 bonus points or a $20 statement credit",
            "premium": "5,000 bonus points or a $50 statement credit",
        }
        return result(False, ["required retention offer has not been made"],
                      ["make_one_retention_offer: " + amounts[tier]], details)
    if retention.get("declined") is not True:
        return result(False, ["customer has not declined the retention offer"],
                      ["obtain_customer_retention_offer_decision"], details)
    return result(True, [], ["call_close_credit_card_account_7834"], details)


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        print(json.dumps(evaluate(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps(result(False, ["invalid evaluator input: " + str(exc)],
                                ["correct_normalized_closure_state"], {}), sort_keys=True))
