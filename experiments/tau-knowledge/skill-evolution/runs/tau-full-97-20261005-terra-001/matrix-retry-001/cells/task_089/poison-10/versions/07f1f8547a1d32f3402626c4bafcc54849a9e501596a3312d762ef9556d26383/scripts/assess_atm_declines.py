#!/usr/bin/env python3
"""Deterministic advisory checks for ATM-decline investigation.

Reads one JSON object from stdin and emits one JSON object to stdout.  This
program does not call banking tools and does not approve or perform an action.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def money(value, field, errors, label):
    """Return a nonnegative Decimal, None for unknown, and report bad input."""
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{label}: {field} must be a non-negative number or null")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label}: {field} must be a non-negative number or null")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{label}: {field} must be a non-negative number or null")
        return None
    return result


def whole_number(value, field, errors, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{label}: {field} must be a non-negative integer or null")
        return None
    return value


def render_amount(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def tri_state(value, field, errors, label):
    if value is None or isinstance(value, bool):
        return value
    errors.append(f"{label}: {field} must be true, false, or null")
    return None


def assess_card(card, index, errors):
    if not isinstance(card, dict):
        errors.append(f"cards[{index}] must be an object")
        return None
    label = card.get("label")
    if not isinstance(label, str) or not label.strip():
        label = f"cards[{index}]"
        errors.append(f"{label}: label must be a non-empty string")

    requested = money(card.get("requested_amount"), "requested_amount", errors, label)
    daily_limit = money(card.get("daily_atm_limit"), "daily_atm_limit", errors, label)
    daily_used = money(card.get("daily_atm_used"), "daily_atm_used", errors, label)
    proposed = money(card.get("proposed_new_limit"), "proposed_new_limit", errors, label)
    age = whole_number(card.get("account_age_days"), "account_age_days", errors, label)
    txn_count = whole_number(card.get("daily_transaction_count"), "daily_transaction_count", errors, label)
    txn_limit = whole_number(card.get("daily_transaction_limit"), "daily_transaction_limit", errors, label)
    overdraft = tri_state(card.get("overdraft_fee_last_30_days"), "overdraft_fee_last_30_days", errors, label)
    recent_increase = tri_state(card.get("temporary_increase_last_24h"), "temporary_increase_last_24h", errors, label)

    remaining = None
    limit_coverage = "unknown"
    if daily_limit is not None and daily_used is not None:
        remaining = max(Decimal("0"), daily_limit - daily_used)
        if requested is not None:
            limit_coverage = "within_known_remaining" if requested <= remaining else "exceeds_known_remaining"

    count_coverage = "unknown"
    if txn_count is not None and txn_limit is not None:
        count_coverage = "within_known_count" if txn_count < txn_limit else "daily_count_exhausted"

    increase_missing = []
    increase_failed = []
    status = card.get("status")
    account_status = card.get("account_status")
    if status is None:
        increase_missing.append("card_status")
    elif status != "ACTIVE":
        increase_failed.append("card must be ACTIVE")
    if account_status is None:
        increase_missing.append("account_status")
    elif account_status != "OPEN":
        increase_failed.append("linked checking account must be OPEN")
    if age is None:
        increase_missing.append("account_age_days")
    elif age < 60:
        increase_failed.append("account must be at least 60 days old")
    if overdraft is None:
        increase_missing.append("overdraft-fee history for last 30 days")
    elif overdraft:
        increase_failed.append("no overdraft fees may exist in the last 30 days")
    if recent_increase is None:
        increase_missing.append("temporary-increase history for last 24 hours")
    elif recent_increase:
        increase_failed.append("only one temporary increase is allowed per card per 24 hours")
    if not card.get("card_id"):
        increase_missing.append("card_id")
    if daily_limit is None:
        increase_missing.append("current daily ATM limit")

    ceiling = daily_limit * Decimal("1.5") if daily_limit is not None else None
    if proposed is not None:
        if daily_limit is None:
            increase_missing.append("current limit needed to validate proposed new limit")
        elif proposed > ceiling:
            increase_failed.append("proposed new limit exceeds 150% of current limit")
        if proposed is not None and daily_limit is not None and proposed <= daily_limit:
            increase_failed.append("proposed new limit must be greater than the current limit")

    mechanical_eligible = (
        proposed is not None
        and not increase_missing
        and not increase_failed
    )
    return {
        "label": label,
        "account_id": card.get("account_id"),
        "card_id": card.get("card_id"),
        "requested_amount": render_amount(requested),
        "daily_atm_limit": render_amount(daily_limit),
        "daily_atm_used": render_amount(daily_used),
        "known_remaining_atm_limit": render_amount(remaining),
        "limit_coverage": limit_coverage,
        "daily_transaction_count_status": count_coverage,
        "temporary_increase": {
            "proposed_new_limit": render_amount(proposed),
            "maximum_allowed_new_limit": render_amount(ceiling),
            "mechanically_eligible_from_supplied_facts": mechanical_eligible,
            "missing_facts": increase_missing,
            "failed_requirements": increase_failed,
            "still_required_outside_this_script": [
                "verified identity, authority, and account/card ownership",
                "customer's explicit confirmation of the new limit and 24-hour duration",
                "available balance and current pending authorization review",
                "fraud, velocity-block, and other card-status investigation",
                "third-party ATM limit review"
            ]
        }
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"invalid JSON: {exc.msg}"], "assessments": []}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"errors": ["top-level JSON value must be an object"], "assessments": []}))
        return
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        print(json.dumps({"errors": ["cards must be a non-empty array"], "assessments": []}))
        return

    errors = []
    assessments = []
    for index, card in enumerate(cards):
        assessment = assess_card(card, index, errors)
        if assessment is not None:
            assessments.append(assessment)
    print(json.dumps({
        "errors": errors,
        "assessments": assessments,
        "disclaimer": "Advisory calculation only. It does not diagnose the decline or authorize a banking action."
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
