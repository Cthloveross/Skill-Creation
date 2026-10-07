#!/usr/bin/env python3
"""Produce a non-executing credit-card closure workflow plan from JSON stdin."""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

ALLOWED_REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
ACTIVE_DISPUTE_STATUSES = {"open", "pending", "under_review", "active", "in_review"}
RETENTION_OFFERS = {
    "entry": {"points": 500, "statement_credit": "5.00"},
    "mid": {"points": 2000, "statement_credit": "20.00"},
    "premium": {"points": 5000, "statement_credit": "50.00"},
}


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_date(value, field):
    if not isinstance(value, str) or len(value) < 10:
        fail(f"{field} must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        fail(f"{field} must begin with a valid YYYY-MM-DD date")


def parse_money(value):
    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        fail("account.current_balance must be a valid monetary amount")


def reward_value(points, representation):
    if representation != "cash_back":
        return None
    try:
        value = Decimal(str(points)) * Decimal("0.01")
    except (InvalidOperation, ValueError):
        fail("account.reward_points must be numeric")
    return f"${value:.2f}"


def main(data):
    account = data.get("account")
    if not isinstance(account, dict):
        fail("account must be an object")
    for field in ("credit_card_account_id", "user_id", "opened_on", "current_balance", "card_tier"):
        if field not in account or account[field] in (None, ""):
            fail(f"account.{field} is required")
    if account["card_tier"] not in RETENTION_OFFERS:
        fail("account.card_tier must be entry, mid, or premium")

    today = parse_date(data.get("now"), "now")
    opened = parse_date(account["opened_on"], "account.opened_on")
    balance = parse_money(account["current_balance"])
    blockers = []
    review_items = []
    account_id = account["credit_card_account_id"]

    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        review_items.append("Account-specific dispute results are required.")
    else:
        for dispute in disputes:
            if not isinstance(dispute, dict):
                review_items.append("A dispute record is malformed.")
                continue
            if dispute.get("credit_card_account_id") != account_id:
                review_items.append("A dispute cannot be associated reliably to the selected account.")
                continue
            status = str(dispute.get("status", "")).strip().lower()
            if not status:
                review_items.append("A selected-account dispute has no status.")
            elif status in ACTIVE_DISPUTE_STATUSES:
                blockers.append("The selected account has an active or pending dispute.")

    orders = data.get("replacement_orders")
    if not isinstance(orders, list):
        review_items.append("Replacement-order results are required.")
    else:
        for order in orders:
            if not isinstance(order, dict):
                review_items.append("A replacement-order record is malformed.")
                continue
            status = str(order.get("status", "")).strip().lower()
            if status not in FINAL_REPLACEMENT_STATUSES:
                blockers.append("The selected account has a replacement card order that is not delivered or cancelled.")
                break

    age_days = (today - opened).days
    if age_days < 60:
        blockers.append("The account has been open fewer than 60 days.")
    if balance != Decimal("0"):
        blockers.append("The outstanding balance is not $0.00.")

    if blockers:
        eligibility = "blocked"
        next_step = "resolve_eligibility_blockers_before_retention"
    elif review_items:
        eligibility = "needs_review"
        next_step = "resolve_account_specific_eligibility_data"
    else:
        eligibility = "eligible"
        history = data.get("closure_history_within_year")
        if history is None:
            next_step = "check_closure_reason_history"
        elif history is True:
            next_step = "obtain_final_closure_confirmation"
        elif history is False:
            reason = data.get("closure_reason")
            if reason not in ALLOWED_REASONS:
                next_step = "obtain_and_log_allowed_closure_reason"
            else:
                retention_status = data.get("retention_status", "not_offered")
                if retention_status == "not_offered":
                    next_step = "address_concern_and_make_one_retention_offer"
                elif retention_status == "offered_accepted":
                    next_step = "apply_accepted_retention_solution"
                elif retention_status == "offered_declined":
                    next_step = ("call_close_tool" if data.get("final_closure_confirmed")
                                 else "obtain_final_closure_confirmation")
                else:
                    next_step = "set_valid_retention_status"
        else:
            next_step = "check_closure_reason_history"

    representation = account.get("rewards_representation")
    if representation not in (None, "cash_back", "points"):
        fail("account.rewards_representation must be cash_back or points when supplied")
    points = account.get("reward_points")
    result = {
        "account": {"credit_card_account_id": account_id, "user_id": account["user_id"]},
        "account_age_days": age_days,
        "eligibility": eligibility,
        "blockers": blockers,
        "review_items": review_items,
        "retention_offer": RETENTION_OFFERS[account["card_tier"]],
        "next_step": next_step,
    }
    if points is not None:
        result["reward_points"] = points
        value = reward_value(points, representation)
        if value is not None:
            result["cash_back_value"] = value
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must contain one JSON object: {exc.msg}")
    if not isinstance(payload, dict):
        fail("stdin must contain a JSON object")
    main(payload)
