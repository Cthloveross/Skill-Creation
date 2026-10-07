#!/usr/bin/env python3
"""Deterministic CLI policy calculations.

Reads one JSON object from stdin and writes one JSON object to stdout.
No external packages, files, account lookups, or banking actions are used.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

RULES = {
    "Entry-tier": {
        "minimum_account_age_days": 120,
        "cooldown_days": 120,
        "utilization_threshold_percent": Decimal("70"),
        "payment_history_months": 6,
        "maximum_increase_fraction": Decimal("0.25"),
    },
    "Mid-tier": {
        "minimum_account_age_days": 90,
        "cooldown_days": 90,
        "utilization_threshold_percent": Decimal("80"),
        "payment_history_months": 3,
        "maximum_increase_fraction": Decimal("0.50"),
    },
    "Premium-tier": {
        "minimum_account_age_days": 60,
        "cooldown_days": 60,
        "utilization_threshold_percent": Decimal("90"),
        "payment_history_months": 3,
        "maximum_increase_fraction": Decimal("0.50"),
    },
}


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    return result


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    text = value.strip()
    candidates = [text[:10], text]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError(f"{field} must begin with YYYY-MM-DD or use MM/DD/YYYY")


def money_string(value):
    return format(value.quantize(Decimal("0.01")), "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    tier = payload.get("tier")
    if tier not in RULES:
        raise ValueError("tier must be Entry-tier, Mid-tier, or Premium-tier")
    rules = RULES[tier]
    limit = decimal_value(payload.get("current_limit"), "current_limit")
    balance = decimal_value(payload.get("current_balance"), "current_balance")
    increase = decimal_value(payload.get("requested_increase"), "requested_increase")
    if limit <= 0:
        raise ValueError("current_limit must be greater than zero")

    maximum = limit * rules["maximum_increase_fraction"]
    utilization = balance * Decimal("100") / limit
    output = {
        "tier": tier,
        "minimum_account_age_days": rules["minimum_account_age_days"],
        "cooldown_days": rules["cooldown_days"],
        "payment_history_months": rules["payment_history_months"],
        "utilization_threshold_percent": str(rules["utilization_threshold_percent"]),
        "maximum_increase_amount": money_string(maximum),
        "requested_increase_amount": money_string(increase),
        "requested_within_cap": increase <= maximum,
        "new_credit_limit": money_string(limit + increase),
        "utilization_percent": str(utilization.quantize(Decimal("0.0001"))),
        "utilization_below_threshold": utilization < rules["utilization_threshold_percent"],
        "account_age_days": None,
        "account_age_eligible": None,
        "cooldown_elapsed_days": None,
        "cooldown_eligible": None,
    }

    as_of = parse_date(payload["as_of"], "as_of") if "as_of" in payload else date.today()
    if "account_open_date" in payload:
        opened = parse_date(payload["account_open_date"], "account_open_date")
        if opened > as_of:
            raise ValueError("account_open_date cannot be after as_of")
        age = (as_of - opened).days
        output["account_age_days"] = age
        output["account_age_eligible"] = age >= rules["minimum_account_age_days"]
    if "prior_approved_request_date" in payload:
        prior = parse_date(payload["prior_approved_request_date"], "prior_approved_request_date")
        if prior > as_of:
            raise ValueError("prior_approved_request_date cannot be after as_of")
        elapsed = (as_of - prior).days
        output["cooldown_elapsed_days"] = elapsed
        output["cooldown_eligible"] = elapsed >= rules["cooldown_days"]
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
