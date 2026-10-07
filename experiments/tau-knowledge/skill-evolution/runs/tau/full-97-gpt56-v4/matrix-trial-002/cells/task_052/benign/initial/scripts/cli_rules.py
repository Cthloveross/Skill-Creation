#!/usr/bin/env python3
"""Deterministic CLI amount and eligibility-rule calculator.

Reads one JSON object from stdin and emits one JSON object on stdout.
It performs no account access and no bank actions.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "Entry-tier": {"min_age_days": 120, "cooldown_days": 120,
                    "utilization_threshold_percent": Decimal("70"),
                    "payment_months": 6, "max_increase_percent": Decimal("25")},
    "Mid-tier": {"min_age_days": 90, "cooldown_days": 90,
                  "utilization_threshold_percent": Decimal("80"),
                  "payment_months": 3, "max_increase_percent": Decimal("50")},
    "Premium-tier": {"min_age_days": 60, "cooldown_days": 60,
                      "utilization_threshold_percent": Decimal("90"),
                      "payment_months": 3, "max_increase_percent": Decimal("50")},
}


def decimal(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")


def json_number(value):
    """Return a non-exponent decimal representation suitable for JSON strings."""
    return format(value, "f")


def optional_nonnegative_int(data, field):
    if field not in data or data[field] is None:
        return None
    value = decimal(data[field], field)
    if value < 0 or value != value.to_integral_value():
        raise ValueError(f"{field} must be a nonnegative integer")
    return int(value)


def optional_nonnegative_decimal(data, field):
    if field not in data or data[field] is None:
        return None
    value = decimal(data[field], field)
    if value < 0:
        raise ValueError(f"{field} must be nonnegative")
    return value


def main(data):
    tier = data.get("tier")
    if tier not in RULES:
        raise ValueError("tier must be Entry-tier, Mid-tier, or Premium-tier")
    rules = RULES[tier]

    limit = decimal(data.get("current_limit"), "current_limit")
    if limit <= 0:
        raise ValueError("current_limit must be greater than zero")

    has_amount = data.get("requested_increase_amount") is not None
    has_percent = data.get("requested_percent") is not None
    if has_amount == has_percent:
        raise ValueError("provide exactly one of requested_increase_amount or requested_percent")

    if has_amount:
        requested = decimal(data["requested_increase_amount"], "requested_increase_amount")
    else:
        percent = decimal(data["requested_percent"], "requested_percent")
        if percent <= 0:
            raise ValueError("requested_percent must be greater than zero")
        requested = limit * percent / Decimal("100")
    if requested <= 0:
        raise ValueError("requested increase must be greater than zero")
    # The submission API accepts integer dollars; do not silently round a request.
    if requested != requested.to_integral_value():
        raise ValueError("requested increase must be an exact whole-dollar amount for submission")

    maximum = (limit * rules["max_increase_percent"] / Decimal("100"))
    proposed = limit + requested
    age = optional_nonnegative_int(data, "account_age_days")
    cooldown = optional_nonnegative_int(data, "days_since_prior_approved_request")
    utilization = optional_nonnegative_decimal(data, "utilization_percent")
    payment_months = optional_nonnegative_int(data, "on_time_months")

    if "prior_request_was_approved" in data and data["prior_request_was_approved"] is not None:
        if not isinstance(data["prior_request_was_approved"], bool):
            raise ValueError("prior_request_was_approved must be boolean")
        prior_approved = data["prior_request_was_approved"]
    else:
        prior_approved = cooldown is not None

    checks = {
        "requested_amount_within_maximum": requested <= maximum,
        "account_age_qualifies": None if age is None else age >= rules["min_age_days"],
        "cooldown_qualifies": (None if cooldown is None else
                                (True if not prior_approved else cooldown >= rules["cooldown_days"])),
        "utilization_qualifies": (None if utilization is None else
                                   utilization < rules["utilization_threshold_percent"]),
        "payment_history_qualifies": (None if payment_months is None else
                                       payment_months >= rules["payment_months"]),
    }
    supplied = [value for value in checks.values() if value is not None]
    return {
        "tier": tier,
        "current_limit": json_number(limit),
        "requested_increase_amount": json_number(requested),
        "proposed_new_credit_limit": json_number(proposed),
        "maximum_increase_amount": json_number(maximum),
        "rules": {
            "minimum_account_age_days": rules["min_age_days"],
            "cooldown_days": rules["cooldown_days"],
            "utilization_must_be_below_percent": json_number(rules["utilization_threshold_percent"]),
            "required_consecutive_on_time_months": rules["payment_months"],
            "maximum_increase_percent": json_number(rules["max_increase_percent"]),
        },
        "checks": checks,
        "all_supplied_checks_pass": all(supplied),
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
