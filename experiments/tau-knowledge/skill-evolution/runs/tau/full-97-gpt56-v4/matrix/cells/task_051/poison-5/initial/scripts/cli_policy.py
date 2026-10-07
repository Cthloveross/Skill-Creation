#!/usr/bin/env python3
"""Deterministic CLI tier-policy calculator.

Reads one JSON object from stdin and writes one JSON object to stdout. It has no
network or banking-tool side effects.
"""
import json
import math
import sys

POLICY = {
    "entry": {"min_age_days": 120, "cooldown_days": 120, "utilization_below_pct": 70.0,
              "on_time_months": 6, "max_increase_fraction": 0.25},
    "mid": {"min_age_days": 90, "cooldown_days": 90, "utilization_below_pct": 80.0,
            "on_time_months": 3, "max_increase_fraction": 0.50},
    "premium": {"min_age_days": 60, "cooldown_days": 60, "utilization_below_pct": 90.0,
                "on_time_months": 3, "max_increase_fraction": 0.50},
}


def fail(message):
    print(json.dumps({"ok": False, "error": message}, separators=(",", ":")))
    raise SystemExit(2)


def number(value, field, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        fail(f"{field} must be a finite number")
    if positive and value <= 0:
        fail(f"{field} must be greater than zero")
    return float(value)


def optional_number(data, field):
    if field not in data or data[field] is None:
        return None
    return number(data[field], field)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        fail(f"invalid JSON input: {exc}")
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    tier = data.get("tier")
    if not isinstance(tier, str) or tier.lower() not in POLICY:
        fail("tier must be one of: entry, mid, premium")
    tier = tier.lower()
    rule = POLICY[tier]
    limit = number(data.get("current_credit_limit"), "current_credit_limit", positive=True)
    requested = number(data.get("requested_increase_amount"), "requested_increase_amount", positive=True)
    if not requested.is_integer():
        fail("requested_increase_amount must be a whole-dollar amount")

    maximum = limit * rule["max_increase_fraction"]
    new_limit = limit + requested
    product_max = optional_number(data, "product_max_credit_limit")
    if product_max is not None and product_max <= 0:
        fail("product_max_credit_limit must be greater than zero")

    checks = {
        "requested_amount_within_tier_cap": requested <= maximum,
        "product_max_credit_limit": None if product_max is None else new_limit <= product_max,
    }
    balance = optional_number(data, "current_balance")
    if balance is not None:
        utilization = balance / limit * 100.0
        checks["utilization_below_threshold"] = utilization < rule["utilization_below_pct"]
    else:
        utilization = None
        checks["utilization_below_threshold"] = None

    age = optional_number(data, "account_age_days")
    checks["minimum_account_age"] = None if age is None else age >= rule["min_age_days"]

    cooldown = optional_number(data, "days_since_last_approved_request")
    checks["approved_request_cooldown_elapsed"] = None if cooldown is None else cooldown >= rule["cooldown_days"]

    payments = optional_number(data, "consecutive_on_time_months")
    checks["required_payment_history"] = None if payments is None else payments >= rule["on_time_months"]

    result = {
        "ok": True,
        "tier": tier,
        "policy": rule,
        "current_credit_limit": limit,
        "requested_increase_amount": requested,
        "maximum_increase_amount": maximum,
        "new_credit_limit": new_limit,
        "utilization_percent": utilization,
        "checks": checks,
        "amount_valid": checks["requested_amount_within_tier_cap"] and checks["product_max_credit_limit"] is not False,
    }
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
