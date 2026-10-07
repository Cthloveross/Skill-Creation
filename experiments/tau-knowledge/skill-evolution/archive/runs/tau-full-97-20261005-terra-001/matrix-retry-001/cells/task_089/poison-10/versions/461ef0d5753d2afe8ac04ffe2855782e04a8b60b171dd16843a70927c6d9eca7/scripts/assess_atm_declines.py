#!/usr/bin/env python3
"""Advisory, deterministic ATM-limit and temporary-increase calculations.

Reads one JSON object from stdin and emits one JSON object to stdout. It never
calls bank tools, decides identity/authority, or performs a banking action.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


ZERO = Decimal("0")
ONE_FIFTY = Decimal("1.5")


def money(value, field, errors, label):
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{label}: {field} must be a non-negative number or null")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label}: {field} must be a non-negative number or null")
        return None
    if not parsed.is_finite() or parsed < ZERO:
        errors.append(f"{label}: {field} must be a non-negative number or null")
        return None
    return parsed


def whole_number(value, field, errors, label):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{label}: {field} must be a non-negative integer or null")
        return None
    return value


def tri_state(value, field, errors, label):
    if value is None or isinstance(value, bool):
        return value
    errors.append(f"{label}: {field} must be true, false, or null")
    return None


def render(amount):
    if amount is None:
        return None
    return format(amount.quantize(Decimal("0.01")), "f")


def assess(card, index, errors):
    if not isinstance(card, dict):
        errors.append(f"cards[{index}] must be an object")
        return None

    label = card.get("label")
    if not isinstance(label, str) or not label.strip():
        label = f"cards[{index}]"
        errors.append(f"{label}: label must be a non-empty string")

    requested = money(card.get("requested_amount"), "requested_amount", errors, label)
    limit = money(card.get("daily_atm_limit"), "daily_atm_limit", errors, label)
    card_used = money(card.get("daily_atm_used"), "daily_atm_used", errors, label)
    confirmed_prior = money(
        card.get("confirmed_prior_atm_withdrawals"),
        "confirmed_prior_atm_withdrawals", errors, label
    )
    proposed = money(card.get("proposed_new_limit"), "proposed_new_limit", errors, label)
    age = whole_number(card.get("account_age_days"), "account_age_days", errors, label)
    overdraft = tri_state(
        card.get("overdraft_fee_last_30_days"),
        "overdraft_fee_last_30_days", errors, label
    )
    recent_increase = tri_state(
        card.get("temporary_increase_last_24h"),
        "temporary_increase_last_24h", errors, label
    )

    # Prefer a directly returned card usage value. Confirmed transaction-history
    # total is the fallback and is separately shown for the customer explanation.
    usage_for_remaining = card_used if card_used is not None else confirmed_prior
    remaining = None
    coverage = "unknown"
    if limit is not None and usage_for_remaining is not None:
        remaining = max(ZERO, limit - usage_for_remaining)
        if requested is not None:
            coverage = (
                "within_known_remaining"
                if requested <= remaining
                else "exceeds_known_remaining"
            )

    confirmed_total = None
    confirmed_total_comparison = "unknown"
    if confirmed_prior is not None and requested is not None:
        confirmed_total = confirmed_prior + requested
        if limit is not None:
            if confirmed_total > limit:
                confirmed_total_comparison = "exceeds_daily_limit"
            else:
                confirmed_total_comparison = "within_daily_limit"

    missing = []
    failed = []
    status = card.get("status")
    account_status = card.get("account_status")
    if status is None:
        missing.append("card_status")
    elif status != "ACTIVE":
        failed.append("card must be ACTIVE")
    if account_status is None:
        missing.append("account_status")
    elif account_status != "OPEN":
        failed.append("linked checking account must be OPEN")
    if age is None:
        missing.append("account_age_days")
    elif age < 60:
        failed.append("account must be at least 60 days old")
    if overdraft is None:
        missing.append("overdraft-fee history for last 30 days")
    elif overdraft:
        failed.append("no overdraft fees may exist in the last 30 days")
    if recent_increase is None:
        missing.append("temporary-increase history for last 24 hours")
    elif recent_increase:
        failed.append("only one temporary increase is allowed per card per 24 hours")
    if not card.get("card_id"):
        missing.append("card_id")
    if limit is None:
        missing.append("current daily ATM limit")

    ceiling = limit * ONE_FIFTY if limit is not None else None
    if proposed is not None:
        if limit is not None and proposed > ceiling:
            failed.append("proposed new limit exceeds 150% of current limit")
        elif limit is not None and proposed <= limit:
            failed.append("proposed new limit must be greater than the current limit")

    eligible = proposed is not None and not missing and not failed
    return {
        "label": label,
        "account_id": card.get("account_id"),
        "card_id": card.get("card_id"),
        "requested_amount": render(requested),
        "daily_atm_limit": render(limit),
        "daily_atm_used": render(card_used),
        "confirmed_prior_atm_withdrawals": render(confirmed_prior),
        "known_remaining_atm_limit": render(remaining),
        "limit_coverage": coverage,
        "confirmed_same_day_total": render(confirmed_total),
        "confirmed_total_vs_daily_limit": confirmed_total_comparison,
        "temporary_increase": {
            "proposed_new_limit": render(proposed),
            "maximum_allowed_new_limit": render(ceiling),
            "mechanically_eligible_from_supplied_facts": eligible,
            "missing_facts": missing,
            "failed_requirements": failed,
            "still_required_outside_this_script": [
                "verified identity, authority, and account/card ownership",
                "customer confirmation of new limit and 24-hour duration",
                "available balance and pending-activity review",
                "fraud, velocity-block, and card-status investigation",
                "third-party ATM limit review",
                "banking-tool request and its result"
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
        result = assess(card, index, errors)
        if result is not None:
            assessments.append(result)
    print(json.dumps({
        "errors": errors,
        "assessments": assessments,
        "disclaimer": "Advisory calculation only; it does not diagnose a decline or authorize a banking action."
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
