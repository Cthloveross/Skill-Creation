#!/usr/bin/env python3
"""Validate a normalized credit-card closure and retention workflow snapshot.

Read one JSON object from stdin and emit one JSON object to stdout. This script is
planning only: it neither invokes banking tools nor changes any account.
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
PERMITTED_POINTS = {500, 2000, 5000}
PERMITTED_CREDITS = {Decimal("5.00"), Decimal("20.00"), Decimal("50.00")}


def invalid(message):
    return {"valid": False, "stage": "input_required", "error": message}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date format") from exc


def parse_money(value):
    if isinstance(value, bool):
        raise ValueError("monetary value cannot be boolean")
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary value") from exc


def status(record):
    return str(record.get("status", "")).strip().lower() if isinstance(record, dict) else ""


def has_nonfinal_replacement(orders):
    return any(status(order) not in FINAL_REPLACEMENT for order in orders)


def validate_authorized_offer(offer):
    """Return normalized authorized offer, or raise ValueError for an invalid shape."""
    if not isinstance(offer, dict) or set(offer) != {"bonus_points"} and set(offer) != {"statement_credit"}:
        raise ValueError("authorized_retention_offer must contain exactly bonus_points or statement_credit")
    if "bonus_points" in offer:
        points = offer["bonus_points"]
        if isinstance(points, bool) or not isinstance(points, int) or points not in PERMITTED_POINTS:
            raise ValueError("authorized bonus_points must be 500, 2000, or 5000")
        return {"bonus_points": points}
    credit = parse_money(offer["statement_credit"])
    if credit not in PERMITTED_CREDITS:
        raise ValueError("authorized statement_credit must be 5, 20, or 50 dollars")
    return {"statement_credit": format(credit, ".2f")}


def result_base(today, opened, balance):
    return {
        "valid": True,
        "stage": None,
        "account_age_days": (today - opened).days,
        "balance_is_zero": balance == Decimal("0"),
        "blockers": [],
        "manual_review": [],
        "next_actions": [],
    }


def final_check_or_close(result, data, retention_skipped):
    if not data["final_replacement_checked"]:
        result["stage"] = "final_replacement_check"
        result["retention_skipped"] = retention_skipped
        result["next_actions"] = [
            "rerun get_pending_replacement_orders_5765 immediately before closure"
        ]
        return result
    if has_nonfinal_replacement(data["final_replacement_orders"]):
        result["stage"] = "resolve_eligibility"
        result["retention_skipped"] = retention_skipped
        result["blockers"].append("final replacement-card check is not clearly final")
        result["next_actions"] = [
            "do not close until every replacement order is delivered or cancelled"
        ]
        return result
    result["stage"] = "close_now"
    result["retention_skipped"] = retention_skipped
    result["next_actions"] = [
        "call close_credit_card_account_7834 with account and user identifiers only",
        "after success, give confirmation/final-statement and 45-day rewards notices",
    ]
    return result


def main(data):
    required = (
        "current_time", "identity_verified", "account_open_date", "current_balance",
        "disputes_checked", "disputes", "replacement_checked", "replacement_orders",
        "prior_history_checked", "prior_year_history_exists", "reason_logged",
        "concern_addressed", "retention_offer_count", "retention_state",
        "final_replacement_checked", "final_replacement_orders",
    )
    missing = [key for key in required if key not in data]
    if missing:
        return invalid("missing required fields: " + ", ".join(missing))
    for key in ("disputes", "replacement_orders", "final_replacement_orders"):
        if not isinstance(data[key], list):
            return invalid(key + " must be a list")
    if data["retention_state"] not in RETENTION_STATES:
        return invalid("retention_state is invalid")
    count = data["retention_offer_count"]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return invalid("retention_offer_count must be a nonnegative integer")

    try:
        today = parse_date(data["current_time"])
        opened = parse_date(data["account_open_date"])
        balance = parse_money(data["current_balance"])
    except ValueError as exc:
        return invalid(str(exc))

    result = result_base(today, opened, balance)
    blockers = result["blockers"]
    review = result["manual_review"]
    if not data["identity_verified"]:
        blockers.append("identity verification is incomplete")
    if not data["disputes_checked"]:
        blockers.append("dispute history has not been checked")
    else:
        dispute_statuses = [status(item) for item in data["disputes"]]
        if any(item in NONFINAL_DISPUTES for item in dispute_statuses):
            blockers.append("an active or pending dispute exists")
        if any(not item for item in dispute_statuses):
            review.append("a dispute record has no usable status")
    if not data["replacement_checked"]:
        blockers.append("replacement orders have not been checked")
    elif has_nonfinal_replacement(data["replacement_orders"]):
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
        result["next_actions"] = [
            "resolve every blocker and manual-review item; do not offer retention or close"
        ]
        return result
    if not data["prior_history_checked"]:
        result["stage"] = "check_closure_reason_history"
        result["next_actions"] = ["call get_closure_reason_history_8293 for the selected account"]
        return result
    if data["prior_year_history_exists"]:
        return final_check_or_close(result, data, retention_skipped=True)

    reason = data.get("reason")
    if reason not in REASONS:
        result["stage"] = "obtain_closure_reason"
        result["next_actions"] = ["obtain one permitted closure reason before logging it"]
        return result
    if not data["reason_logged"]:
        result["stage"] = "log_closure_reason"
        result["next_actions"] = [
            "log only credit_card_account_id, user_id, and closure_reason"
        ]
        return result
    if not data["concern_addressed"]:
        result["stage"] = "address_closure_concern"
        result["next_actions"] = ["address the stated concern before the one retention offer"]
        return result

    state = data["retention_state"]
    if count > 1:
        return invalid("more than one retention offer is not permitted")
    if state == "not_offered" and count != 0:
        return invalid("not_offered requires retention_offer_count of 0")
    if state in {"offered_pending", "declined", "accepted"} and count != 1:
        return invalid("a retention response state requires exactly one prior offer")

    if state == "not_offered":
        try:
            if "authorized_retention_offer" in data:
                offer = validate_authorized_offer(data["authorized_retention_offer"])
            else:
                tier = data.get("card_tier")
                if tier not in OFFERS:
                    result["stage"] = "tier_classification_required"
                    result["manual_review"].append(
                        "authoritative tier classification or configured retention offer is required"
                    )
                    result["next_actions"] = [
                        "obtain authoritative offer authorization before any final closure decision",
                        "do not transfer, process closure, or solicit a closure confirmation",
                    ]
                    return result
                offer = OFFERS[tier]
        except ValueError as exc:
            return invalid(str(exc))
        result["stage"] = "make_retention_offer"
        result["retention_offer"] = offer
        result["next_actions"] = [
            "make exactly one concrete retention_offer and await the customer response",
            "do not ask whether to proceed with closure before making that offer",
        ]
        return result
    if state == "offered_pending":
        result["stage"] = "await_retention_decision"
        result["next_actions"] = [
            "await the response; do not repeat, replace, or stack the retention offer"
        ]
        return result
    if state == "accepted":
        result["stage"] = "retain_no_close"
        result["next_actions"] = ["complete the accepted resolution or offer; do not close"]
        return result
    return final_check_or_close(result, data, retention_skipped=False)


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        output = main(payload) if isinstance(payload, dict) else invalid("input must be a JSON object")
    except json.JSONDecodeError:
        output = invalid("stdin must contain valid JSON")
    print(json.dumps(output, sort_keys=True))
