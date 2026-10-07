#!/usr/bin/env python3
"""Evaluate documented credit-limit-increase policy from normalized JSON input.

Input and output are JSON objects on stdin/stdout. This helper is deliberately
read-only: the calling agent performs all banking-tool calls and supplies the
reviewed facts.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry-tier": {
        "age_days": 120,
        "cooldown_days": 120,
        "utilization_lt": Decimal("70"),
        "payment_months": 6,
        "max_fraction": Decimal("0.25"),
    },
    "mid-tier": {
        "age_days": 90,
        "cooldown_days": 90,
        "utilization_lt": Decimal("80"),
        "payment_months": 3,
        "max_fraction": Decimal("0.50"),
    },
    "premium-tier": {
        "age_days": 60,
        "cooldown_days": 60,
        "utilization_lt": Decimal("90"),
        "payment_months": 3,
        "max_fraction": Decimal("0.50"),
    },
}


def fail(message):
    return {"ok": False, "error": message}


def tier_key(value):
    if not isinstance(value, str):
        raise ValueError("tier must be a string")
    key = value.strip().lower().replace("_", "-").replace(" ", "-")
    if key not in POLICY:
        raise ValueError("tier must be entry-tier, mid-tier, or premium-tier")
    return key


def money(value, field):
    if isinstance(value, bool):
        raise ValueError(field + " must be a decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be a decimal number")
    if not result.is_finite() or result < 0:
        raise ValueError(field + " must be a non-negative finite number")
    return result


def whole_dollars(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(field + " must be a non-negative integer number of dollars")
    return Decimal(value)


def as_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(field + " must be a nonempty date string")
    text = value.strip()
    candidates = [text]
    if len(text) >= 10:
        candidates.append(text[:10])
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        raise ValueError(field + " must use YYYY-MM-DD, ISO timestamp, or MM/DD/YYYY")


def boolean(value, field):
    if not isinstance(value, bool):
        raise ValueError(field + " must be true or false")
    return value


def integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(field + " must be a non-negative integer")
    return value


def amount_result(data, policy):
    limit = money(data.get("current_credit_limit"), "current_credit_limit")
    requested = whole_dollars(data.get("requested_increase_amount"), "requested_increase_amount")
    maximum = limit * policy["max_fraction"]
    within = requested <= maximum
    return {
        "max_increase_amount": format(maximum, ".2f"),
        "requested_increase_amount": format(requested, ".2f"),
        "new_credit_limit": format(limit + requested, ".2f"),
        "amount_within_limit": within,
        "submission_permitted": within,
    }


def evaluate(data, tier, policy):
    amount = amount_result(data, policy)
    opened = as_date(data.get("account_open_date"), "account_open_date")
    today = as_date(data.get("current_date"), "current_date")
    if opened > today:
        raise ValueError("account_open_date cannot be after current_date")
    balance = money(data.get("current_balance"), "current_balance")
    limit = money(data.get("current_credit_limit"), "current_credit_limit")
    if limit == 0:
        raise ValueError("current_credit_limit must be greater than zero for utilization")
    account_current = boolean(data.get("account_current"), "account_current")
    past_due = money(data.get("past_due_amount"), "past_due_amount")
    active_disputes = boolean(data.get("active_disputes"), "active_disputes")
    pending_replacement = boolean(data.get("pending_replacement"), "pending_replacement")
    paid_months = integer(data.get("consecutive_on_time_months"), "consecutive_on_time_months")

    latest = data.get("last_approved_request_date")
    if latest is None:
        cooldown_elapsed = True
        days_since_approved = None
    else:
        approved_date = as_date(latest, "last_approved_request_date")
        if approved_date > today:
            raise ValueError("last_approved_request_date cannot be after current_date")
        days_since_approved = (today - approved_date).days
        cooldown_elapsed = days_since_approved >= policy["cooldown_days"]

    account_age_days = (today - opened).days
    utilization = (balance / limit) * Decimal("100")
    checks = {
        "requested_amount_within_limit": amount["amount_within_limit"],
        "minimum_account_age": account_age_days >= policy["age_days"],
        "cooldown_elapsed": cooldown_elapsed,
        "no_active_disputes": not active_disputes,
        "no_pending_replacement": not pending_replacement,
        "account_good_standing": account_current and past_due <= 0,
        "utilization_below_threshold": utilization < policy["utilization_lt"],
        "sufficient_payment_history": paid_months >= policy["payment_months"],
    }
    reason_order = [
        ("requested_amount_within_limit", "requested_amount_exceeds_limit"),
        ("minimum_account_age", "insufficient_account_age"),
        ("cooldown_elapsed", "cooldown_period_active"),
        ("no_active_disputes", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("account_good_standing", "past_due_balance"),
        ("utilization_below_threshold", "high_utilization"),
        ("sufficient_payment_history", "insufficient_payment_history"),
    ]
    denial_reason = next((reason for check, reason in reason_order if not checks[check]), None)
    return {
        "ok": True,
        "tier": tier,
        "policy": {
            "minimum_account_age_days": policy["age_days"],
            "cooldown_days": policy["cooldown_days"],
            "utilization_must_be_below_percent": format(policy["utilization_lt"], "f"),
            "required_consecutive_on_time_months": policy["payment_months"],
        },
        **amount,
        "account_age_days": account_age_days,
        "days_since_last_approved_request": days_since_approved,
        "utilization_percent": format(utilization, ".4f"),
        "checks": checks,
        "eligible": all(checks.values()),
        "denial_reason": denial_reason,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        tier = tier_key(data.get("tier"))
        policy = POLICY[tier]
        mode = data.get("mode")
        if mode == "amount_check":
            result = {"ok": True, "tier": tier, **amount_result(data, policy)}
        elif mode == "evaluate":
            result = evaluate(data, tier, policy)
        else:
            raise ValueError("mode must be amount_check or evaluate")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = fail(str(exc))
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
