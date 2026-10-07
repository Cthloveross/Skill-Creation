#!/usr/bin/env python3
"""Evaluate a normalized credit-card closure workflow snapshot.

Reads one JSON object from stdin and writes one JSON object to stdout.  This is
planning/validation only: it never invokes banking tools or changes an account.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
NONFINAL_DISPUTE_STATUSES = {"open", "under_review", "pending", "active", "in_progress"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled", "canceled"}
OFFERS = {
    "entry": {"points": 500, "statement_credit": "5.00"},
    "mid": {"points": 2000, "statement_credit": "20.00"},
    "premium": {"points": 5000, "statement_credit": "50.00"},
}


def error(message):
    return {"valid": False, "error": message, "stage": "input_required"}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # ISO timestamps, including offsets, are useful when supplied by a runtime.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date format") from exc


def money(value):
    if isinstance(value, bool):
        raise ValueError("balance cannot be boolean")
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc


def status(record):
    if not isinstance(record, dict):
        return ""
    return str(record.get("status", "")).strip().lower()


def main(data):
    required = [
        "current_time", "identity_verified", "account_open_date", "current_balance",
        "disputes_checked", "disputes", "replacement_checked", "replacement_orders",
        "prior_history_checked", "prior_year_history_exists", "retention_state",
        "final_replacement_checked",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        return error("missing required fields: " + ", ".join(missing))
    if not isinstance(data["disputes"], list) or not isinstance(data["replacement_orders"], list):
        return error("disputes and replacement_orders must be lists")
    if data["retention_state"] not in {"not_offered", "offered_pending", "declined", "accepted"}:
        return error("retention_state is invalid")
    try:
        today = parse_date(data["current_time"])
        opened = parse_date(data["account_open_date"])
        balance = money(data["current_balance"])
    except ValueError as exc:
        return error(str(exc))

    blockers = []
    review = []
    if not data["identity_verified"]:
        blockers.append("identity verification is incomplete")
    if not data["disputes_checked"]:
        blockers.append("dispute history has not been checked")
    else:
        dispute_states = [status(item) for item in data["disputes"]]
        if any(s in NONFINAL_DISPUTE_STATUSES for s in dispute_states):
            blockers.append("an active or pending dispute exists")
        if any(not s for s in dispute_states):
            review.append("a dispute record has no usable status")
    if not data["replacement_checked"]:
        blockers.append("replacement orders have not been checked")
    else:
        replacement_states = [status(item) for item in data["replacement_orders"]]
        if any(s not in FINAL_REPLACEMENT_STATUSES for s in replacement_states):
            blockers.append("a replacement-card order is not clearly final")
    if (today - opened).days < 60:
        blockers.append("account has been open fewer than 60 days")
    if balance != Decimal("0"):
        blockers.append("outstanding balance is not $0.00")

    result = {
        "valid": True,
        "account_age_days": (today - opened).days,
        "balance_is_zero": balance == Decimal("0"),
        "blockers": blockers,
        "manual_review": review,
        "stage": None,
        "next_actions": [],
    }
    if "reward_points" in data:
        try:
            points = Decimal(str(data["reward_points"]).replace(",", ""))
            result["cash_back_value_at_one_cent_per_point"] = str((points * Decimal("0.01")).quantize(Decimal("0.01")))
        except (InvalidOperation, ValueError):
            return error("reward_points must be numeric when supplied")

    if blockers or review:
        result["stage"] = "resolve_eligibility"
        result["next_actions"] = ["resolve every blocker; do not make a retention offer or close"]
        return result
    if not data["prior_history_checked"]:
        result["stage"] = "check_closure_reason_history"
        result["next_actions"] = ["call get_closure_reason_history_8293 for this account"]
        return result
    if data["prior_year_history_exists"]:
        if not data["final_replacement_checked"]:
            result["stage"] = "final_replacement_check"
            result["next_actions"] = ["rerun get_pending_replacement_orders_5765 immediately before closure"]
        else:
            result["stage"] = "close_now"
            result["next_actions"] = ["call close_credit_card_account_7834 and provide post-closure notices after success"]
        result["retention_skipped"] = True
        return result

    reason = data.get("reason")
    if reason not in REASONS:
        result["stage"] = "obtain_closure_reason"
        result["next_actions"] = ["obtain one permitted closure reason before logging it"]
        return result
    if not data.get("reason_logged", False):
        result["stage"] = "log_closure_reason"
        result["next_actions"] = ["call log_credit_card_closure_reason_4521 with only its three permitted fields"]
        return result
    if data["retention_state"] == "accepted":
        result["stage"] = "retain_no_close"
        result["next_actions"] = ["complete the accepted retention resolution; do not close"]
        return result
    if data["retention_state"] != "declined":
        tier = data.get("card_tier")
        result["stage"] = "make_or_wait_for_retention_offer"
        result["next_actions"] = ["address the reason, make exactly one tier-appropriate offer, and await the customer decision"]
        if tier in OFFERS:
            result["retention_offer"] = OFFERS[tier]
        else:
            result["manual_review"].append("authoritative card tier is required before stating an offer")
        return result
    if not data["final_replacement_checked"]:
        result["stage"] = "final_replacement_check"
        result["next_actions"] = ["rerun get_pending_replacement_orders_5765 immediately before closure"]
        return result
    result["stage"] = "close_now"
    result["next_actions"] = ["call close_credit_card_account_7834 and provide post-closure notices after success"]
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            output = error("input must be a JSON object")
        else:
            output = main(payload)
    except json.JSONDecodeError:
        output = error("stdin must contain valid JSON")
    print(json.dumps(output, sort_keys=True))
