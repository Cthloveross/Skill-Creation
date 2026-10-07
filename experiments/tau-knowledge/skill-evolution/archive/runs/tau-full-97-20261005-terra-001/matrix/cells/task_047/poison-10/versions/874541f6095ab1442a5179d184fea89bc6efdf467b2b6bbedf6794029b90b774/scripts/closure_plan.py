#!/usr/bin/env python3
"""Produce a conservative closure-workflow plan from normalized runtime checks.

Input: one JSON object described in SKILL.md on stdin.
Output: one JSON object containing eligibility gates and the next required stage.
This program performs no I/O other than stdin/stdout and never executes banking actions.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

FINAL_DISPUTE_STATUSES = {"closed", "resolved"}
FINAL_REPLACEMENT_STATUSES = {"delivered", "cancelled"}
VALID_REASONS = {
    "annual_fee", "not_using_card", "found_better_card", "unhappy_with_rewards",
    "simplifying_finances", "negative_experience", "other",
}
VALID_RETENTION_DECISIONS = {"pending", "accepted", "declined"}


def normalized(value):
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def parse_date(value):
    """Accept an ISO date or a timestamp whose first token is an ISO date."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    token = value.strip().split()[0]
    try:
        return date.fromisoformat(token)
    except ValueError:
        # Permit full ISO datetime values as an explicitly supplied runtime value.
        return datetime.fromisoformat(token.replace("Z", "+00:00")).date()


def parse_balance(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing balance")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid balance") from exc


def as_bool(data, key, reviews):
    value = data.get(key)
    if isinstance(value, bool):
        return value
    reviews.append(f"{key} must be supplied as true or false")
    return False


def status_list(data, key, checked, reviews):
    value = data.get(key)
    if not checked:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        reviews.append(f"{key} must be a list of status strings after the check is run")
        return []
    return [normalized(item) for item in value]


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "Input must be a single valid JSON object", "detail": str(exc)}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"error": "Input must be a JSON object"}))
        return

    blockers = []
    reviews = []

    identity_verified = as_bool(data, "identity_verified", reviews)
    owner_confirmed = as_bool(data, "account_owner_confirmed", reviews)
    if not identity_verified:
        blockers.append("Customer identity has not been verified.")
    if not owner_confirmed:
        blockers.append("Account ownership or authority has not been confirmed.")

    try:
        balance = parse_balance(data.get("balance"))
        if balance != Decimal("0"):
            blockers.append("Outstanding balance is not exactly $0.00.")
    except ValueError:
        reviews.append("A current, parseable account balance is required.")

    try:
        opened = parse_date(data.get("account_open_date"))
        today = parse_date(data.get("current_time"))
        age_days = (today - opened).days
        if age_days < 0:
            reviews.append("Account opening date is later than the supplied current date.")
        elif age_days < 60:
            blockers.append("Account has been open fewer than 60 days.")
    except ValueError:
        age_days = None
        reviews.append("Account opening date and current date are required to verify 60-day age.")

    disputes_checked = as_bool(data, "disputes_checked", reviews)
    disputes = status_list(data, "dispute_statuses", disputes_checked, reviews)
    if not disputes_checked:
        blockers.append("Dispute history has not been checked.")
    else:
        unresolved = [status for status in disputes if status not in FINAL_DISPUTE_STATUSES]
        if unresolved:
            blockers.append("Unresolved or unrecognized dispute status: " + ", ".join(unresolved))

    replacements_checked = as_bool(data, "replacement_orders_checked", reviews)
    replacements = status_list(data, "replacement_order_statuses", replacements_checked, reviews)
    if not replacements_checked:
        blockers.append("Replacement-card orders have not been checked.")
    else:
        nonfinal = [status for status in replacements if status not in FINAL_REPLACEMENT_STATUSES]
        if nonfinal:
            blockers.append("Pending or unrecognized replacement-order status: " + ", ".join(nonfinal))

    eligible_now = not blockers and not reviews
    history_checked = as_bool(data, "history_checked", reviews)
    prior = data.get("prior_closure_reason_within_year")
    reason = data.get("closure_reason")
    reason_logged = as_bool(data, "closure_reason_logged", reviews)
    concern_addressed = as_bool(data, "concern_addressed", reviews)
    decision = data.get("retention_decision", "pending")
    final_confirmation = as_bool(data, "final_confirmation", reviews)
    preclose_recheck = as_bool(data, "preclose_recheck_completed", reviews)

    next_stage = "resolve_eligibility"
    closure_allowed = False

    if eligible_now:
        if not history_checked:
            next_stage = "check_prior_closure_reason_history"
        elif not isinstance(prior, bool):
            next_stage = "manual_review_prior_closure_reason_history"
            reviews.append("prior_closure_reason_within_year must be true or false after history check.")
        elif prior:
            if not final_confirmation:
                next_stage = "obtain_final_closure_confirmation"
            elif not preclose_recheck:
                next_stage = "perform_immediate_preclose_recheck"
            else:
                next_stage = "close_account"
                closure_allowed = True
        elif not isinstance(reason, str) or reason not in VALID_REASONS:
            next_stage = "collect_normalized_closure_reason"
        elif not reason_logged:
            next_stage = "log_closure_reason"
        elif not concern_addressed:
            next_stage = "address_customer_concern"
        elif decision not in VALID_RETENTION_DECISIONS:
            next_stage = "record_valid_retention_decision"
            reviews.append("retention_decision must be pending, accepted, or declined.")
        elif decision == "pending":
            next_stage = "make_one_tier_based_retention_offer"
        elif decision == "accepted":
            next_stage = "complete_accepted_retention_action_do_not_close"
        elif not final_confirmation:
            next_stage = "obtain_final_closure_confirmation"
        elif not preclose_recheck:
            next_stage = "perform_immediate_preclose_recheck"
        else:
            next_stage = "close_account"
            closure_allowed = True

    result = {
        "eligible_now": eligible_now,
        "account_age_days": age_days,
        "blockers": blockers,
        "manual_review": reviews,
        "next_stage": next_stage,
        "closure_action_allowed": closure_allowed,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
