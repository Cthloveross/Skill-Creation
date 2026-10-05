#!/usr/bin/env python3
"""Validate a normalized credit-card closure and retention workflow snapshot.

Reads a JSON object from stdin and emits a JSON object on stdout. This script is
planning only: it neither invokes banking tools nor changes an account.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
RETENTION_STATES = {"not_offered", "offered_pending", "declined", "accepted"}
NONFINAL_DISPUTES = {"open", "under_review", "pending", "active", "in_progress"}
FINAL_REPLACEMENT = {"delivered", "cancelled", "canceled"}
OFFERS = {
    "entry": {"bonus_points": 500, "statement_credit": "5.00"},
    "mid": {"bonus_points": 2000, "statement_credit": "20.00"},
    "premium": {"bonus_points": 5000, "statement_credit": "50.00"},
}


def invalid(message):
    return {"valid": False, "stage": "input_required", "error": message}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date format") from exc


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("balance cannot be boolean")
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc


def record_status(record):
    if not isinstance(record, dict):
        return ""
    return str(record.get("status", "")).strip().lower()


def unresolved_replacement(orders):
    return any(record_status(order) not in FINAL_REPLACEMENT for order in orders)


def base_result(today, opened, balance):
    return {
        "valid": True,
        "stage": None,
        "account_age_days": (today - opened).days,
        "balance_is_zero": balance == Decimal("0"),
        "blockers": [],
        "manual_review": [],
        "next_actions": [],
    }


def main(data):
    required = (
        "current_time", "identity_verified", "account_open_date", "current_balance",
        "disputes_checked", "disputes", "replacement_checked", "replacement_orders",
        "prior_history_checked", "prior_year_history_exists", "reason_logged",
        "concern_addressed", "retention_state", "final_replacement_checked",
        "final_replacement_orders",
    )
    missing = [name for name in required if name not in data]
    if missing:
        return invalid("missing required fields: " + ", ".join(missing))
    if not isinstance(data["disputes"], list):
        return invalid("disputes must be a list")
    if not isinstance(data["replacement_orders"], list):
        return invalid("replacement_orders must be a list")
    if not isinstance(data["final_replacement_orders"], list):
        return invalid("final_replacement_orders must be a list")
    if data["retention_state"] not in RETENTION_STATES:
        return invalid("retention_state is invalid")
    try:
        today = parse_date(data["current_time"])
        opened = parse_date(data["account_open_date"])
        balance = parse_money(data["current_balance"])
    except ValueError as exc:
        return invalid(str(exc))

    result = base_result(today, opened, balance)
    blockers = result["blockers"]
    review = result["manual_review"]
    if not data["identity_verified"]:
        blockers.append("identity verification is incomplete")
    if not data["disputes_checked"]:
        blockers.append("dispute history has not been checked")
    else:
        statuses = [record_status(item) for item in data["disputes"]]
        if any(state in NONFINAL_DISPUTES for state in statuses):
            blockers.append("an active or pending dispute exists")
        if any(not state for state in statuses):
            review.append("a dispute record has no usable status")
    if not data["replacement_checked"]:
        blockers.append("replacement orders have not been checked")
    elif unresolved_replacement(data["replacement_orders"]):
        blockers.append("a replacement-card order is not clearly final")
    if (today - opened).days < 60:
        blockers.append("account has been open fewer than 60 days")
    if balance != Decimal("0"):
        blockers.append("outstanding balance is not $0.00")

    if "reward_points" in data:
        try:
            points = Decimal(str(data["reward_points"]).replace(",", ""))
            result["cash_back_value_at_one_cent_per_point"] = str(
                (points * Decimal("0.01")).quantize(Decimal("0.01"))
            )
        except (InvalidOperation, ValueError):
            return invalid("reward_points must be numeric when supplied")

    if blockers or review:
        result["stage"] = "resolve_eligibility"
        result["next_actions"] = ["resolve every blocker and manual-review item; do not offer retention or close"]
        return result

    if not data["prior_history_checked"]:
        result["stage"] = "check_closure_reason_history"
        result["next_actions"] = ["call get_closure_reason_history_8293 for the selected account"]
        return result

    # Prior-year records are the sole path that skips a retention offer.
    if data["prior_year_history_exists"]:
        return final_check_or_close(result, data, retention_skipped=True)

    reason = data.get("reason")
    if reason not in REASONS:
        result["stage"] = "obtain_closure_reason"
        result["next_actions"] = ["obtain one permitted closure reason before logging it"]
        return result
    if not data["reason_logged"]:
        result["stage"] = "log_closure_reason"
        result["next_actions"] = ["log the reason with only the three documented arguments"]
        return result
    if not data["concern_addressed"]:
        result["stage"] = "address_closure_concern"
        result["next_actions"] = ["address the stated concern before making the single retention offer"]
        return result

    state = data["retention_state"]
    if state == "not_offered":
        tier = data.get("card_tier")
        if tier not in OFFERS:
            result["stage"] = "determine_card_tier_or_escalate"
            result["manual_review"].append("authoritative card-tier classification is unavailable")
            result["next_actions"] = [
                "determine tier from authoritative information or escalate",
                "do not solicit a final closure decision before the required offer",
            ]
            return result
        result["stage"] = "make_retention_offer"
        result["retention_offer"] = OFFERS[tier]
        result["next_actions"] = [
            "make exactly this one tier-appropriate offer and await the customer decision",
            "do not ask whether to proceed with closure before making the offer",
        ]
        return result
    if state == "offered_pending":
        result["stage"] = "await_retention_decision"
        result["next_actions"] = ["await the customer's response; do not repeat or replace the offer"]
        return result
    if state == "accepted":
        result["stage"] = "retain_no_close"
        result["next_actions"] = ["complete the accepted resolution or offer; do not close"]
        return result
    return final_check_or_close(result, data, retention_skipped=False)


def final_check_or_close(result, data, retention_skipped):
    if not data["final_replacement_checked"]:
        result["stage"] = "final_replacement_check"
        result["next_actions"] = ["rerun get_pending_replacement_orders_5765 immediately before closure"]
        result["retention_skipped"] = retention_skipped
        return result
    if unresolved_replacement(data["final_replacement_orders"]):
        result["stage"] = "resolve_eligibility"
        result["blockers"].append("final replacement-card check is not clearly final")
        result["next_actions"] = ["do not close until every replacement order is delivered or cancelled"]
        result["retention_skipped"] = retention_skipped
        return result
    result["stage"] = "close_now"
    result["retention_skipped"] = retention_skipped
    result["next_actions"] = [
        "call close_credit_card_account_7834 with account and user identifiers only",
        "after success, provide the 45-day rewards-redemption notice",
    ]
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        output = main(payload) if isinstance(payload, dict) else invalid("input must be a JSON object")
    except json.JSONDecodeError:
        output = invalid("stdin must contain valid JSON")
    print(json.dumps(output, sort_keys=True))
