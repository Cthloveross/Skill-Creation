#!/usr/bin/env python3
"""Read-only evaluator for documented credit-limit-increase policy.

Reads one JSON object from stdin and emits one JSON object to stdout. The caller
must perform submission and all banking-tool reviews separately.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry-tier": {"age": 120, "cooldown": 120, "util": Decimal("70"), "months": 6, "fraction": Decimal(".25")},
    "mid-tier": {"age": 90, "cooldown": 90, "util": Decimal("80"), "months": 3, "fraction": Decimal(".50")},
    "premium-tier": {"age": 60, "cooldown": 60, "util": Decimal("90"), "months": 3, "fraction": Decimal(".50")},
}


def decimal(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative decimal number")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a non-negative decimal number")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be a non-negative decimal number")
    return value


def integer(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def flag(value, field):
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be true or false")
    return value


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    text = value.strip()
    for candidate in (text, text[:10]):
        for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        raise ValueError(f"{field} must be YYYY-MM-DD, MM/DD/YYYY, or ISO timestamp")


def get_tier(value):
    if not isinstance(value, str):
        raise ValueError("tier must be a string")
    key = value.strip().lower().replace("_", "-").replace(" ", "-")
    if key not in POLICY:
        raise ValueError("tier must be entry-tier, mid-tier, or premium-tier")
    return key


def amount_check(data, policy):
    limit = decimal(data.get("current_credit_limit"), "current_credit_limit")
    requested = Decimal(integer(data.get("requested_increase_amount"), "requested_increase_amount"))
    maximum = limit * policy["fraction"]
    within = requested <= maximum
    return {
        "max_increase_amount": format(maximum, ".2f"),
        "requested_increase_amount": format(requested, ".2f"),
        "new_credit_limit": format(limit + requested, ".2f"),
        "amount_within_limit": within,
        "submission_permitted": within,
    }


def evaluate(data, tier, policy):
    amount = amount_check(data, policy)
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    today = parse_date(data.get("current_date"), "current_date")
    if opened > today:
        raise ValueError("account_open_date cannot be after current_date")
    limit = decimal(data.get("current_credit_limit"), "current_credit_limit")
    if limit == 0:
        raise ValueError("current_credit_limit must be greater than zero")
    balance = decimal(data.get("current_balance"), "current_balance")
    past_due = decimal(data.get("past_due_amount"), "past_due_amount")
    current = flag(data.get("account_current"), "account_current")
    disputes = flag(data.get("active_disputes"), "active_disputes")
    replacement = flag(data.get("pending_replacement"), "pending_replacement")
    on_time_months = integer(data.get("consecutive_on_time_months"), "consecutive_on_time_months")

    prior = data.get("last_approved_request_date")
    if prior is None:
        elapsed = True
        days_since = None
    else:
        prior_date = parse_date(prior, "last_approved_request_date")
        if prior_date > today:
            raise ValueError("last_approved_request_date cannot be after current_date")
        days_since = (today - prior_date).days
        elapsed = days_since >= policy["cooldown"]

    age_days = (today - opened).days
    utilization = balance / limit * Decimal("100")
    checks = {
        "requested_amount_within_limit": amount["amount_within_limit"],
        "minimum_account_age": age_days >= policy["age"],
        "cooldown_elapsed": elapsed,
        "no_active_disputes": not disputes,
        "no_pending_replacement": not replacement,
        "account_good_standing": current and past_due == 0,
        "utilization_below_threshold": utilization < policy["util"],
        "sufficient_payment_history": on_time_months >= policy["months"],
    }
    reasons = (
        ("requested_amount_within_limit", "requested_amount_exceeds_limit"),
        ("minimum_account_age", "insufficient_account_age"),
        ("cooldown_elapsed", "cooldown_period_active"),
        ("no_active_disputes", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("account_good_standing", "past_due_balance"),
        ("utilization_below_threshold", "high_utilization"),
        ("sufficient_payment_history", "insufficient_payment_history"),
    )
    denial = next((reason for check, reason in reasons if not checks[check]), None)
    return {
        "ok": True,
        "tier": tier,
        **amount,
        "account_age_days": age_days,
        "days_since_last_approved_request": days_since,
        "utilization_percent": format(utilization, ".4f"),
        "checks": checks,
        "eligible": all(checks.values()),
        "denial_reason": denial,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        tier = get_tier(data.get("tier"))
        if data.get("mode") == "amount_check":
            result = {"ok": True, "tier": tier, **amount_check(data, POLICY[tier])}
        elif data.get("mode") == "evaluate":
            result = evaluate(data, tier, POLICY[tier])
        else:
            raise ValueError("mode must be amount_check or evaluate")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        result = {"ok": False, "error": str(exc)}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
