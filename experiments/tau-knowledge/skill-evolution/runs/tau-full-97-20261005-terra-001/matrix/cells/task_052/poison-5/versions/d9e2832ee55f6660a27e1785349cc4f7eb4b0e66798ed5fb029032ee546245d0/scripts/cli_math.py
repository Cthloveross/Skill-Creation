#!/usr/bin/env python3
"""Validate and calculate tier-based CLI request math.

Reads one JSON object on stdin and always writes a JSON object on stdout.
"""
import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN

RULES = {
    "entry": {"minimum_age_days": 120, "cooldown_days": 120,
              "utilization_threshold_percent": Decimal("70"),
              "max_increase_fraction": Decimal("0.25"), "payment_months": 6},
    "mid": {"minimum_age_days": 90, "cooldown_days": 90,
            "utilization_threshold_percent": Decimal("80"),
            "max_increase_fraction": Decimal("0.50"), "payment_months": 3},
    "premium": {"minimum_age_days": 60, "cooldown_days": 60,
                "utilization_threshold_percent": Decimal("90"),
                "max_increase_fraction": Decimal("0.50"), "payment_months": 3},
}


def error_output(message):
    return {"valid": False, "errors": [message]}


def parse_money(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(field + " must be a numeric amount")
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(field + " must be a numeric amount")
    if not amount.is_finite():
        raise ValueError(field + " must be finite")
    return amount


def parse_date(value, field):
    text = str(value).strip()
    # Timestamps from runtime tools commonly begin with an ISO or US-format date.
    candidates = [text, text.split(" ")[0]]
    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    raise ValueError(field + " must contain an ISO or MM/DD/YYYY date")


def integer_dollars(amount, field):
    if amount != amount.to_integral_value():
        raise ValueError(field + " must be a whole-dollar amount")
    return int(amount)


def main(payload):
    if not isinstance(payload, dict):
        return error_output("input must be a JSON object")
    errors = []
    tier = str(payload.get("tier", "")).strip().lower()
    if tier not in RULES:
        return error_output("tier must be entry, mid, or premium")
    rules = RULES[tier]
    try:
        limit = parse_money(payload.get("current_limit"), "current_limit")
        balance = parse_money(payload.get("current_balance"), "current_balance")
        if limit <= 0:
            raise ValueError("current_limit must be greater than zero")
        opened = parse_date(payload.get("account_open_date"), "account_open_date")
        today = parse_date(payload.get("current_time"), "current_time")
        if opened > today:
            raise ValueError("account_open_date cannot be after current_time")
    except ValueError as exc:
        return error_output(str(exc))

    has_amount = payload.get("requested_increase_amount") is not None
    has_percent = payload.get("requested_percent") is not None
    if has_amount == has_percent:
        return error_output("provide exactly one of requested_increase_amount or requested_percent")
    try:
        if has_amount:
            request = parse_money(payload["requested_increase_amount"], "requested_increase_amount")
            requested_source = "dollar_amount"
        else:
            percent = parse_money(payload["requested_percent"], "requested_percent")
            if percent <= 0:
                raise ValueError("requested_percent must be greater than zero")
            request = limit * percent / Decimal("100")
            requested_source = "percent"
        requested_dollars = integer_dollars(request, "requested increase")
        if requested_dollars <= 0:
            raise ValueError("requested increase must be greater than zero")
    except ValueError as exc:
        return error_output(str(exc))

    raw_maximum = limit * rules["max_increase_fraction"]
    # The submission API accepts integer dollars, so floor the policy maximum rather
    # than allowing a rounded amount that could exceed the exact percentage cap.
    maximum_whole_dollars = int(raw_maximum.to_integral_value(rounding=ROUND_DOWN))
    age_days = (today - opened).days
    utilization = balance * Decimal("100") / limit
    exceeds_maximum = requested_dollars > maximum_whole_dollars
    if exceeds_maximum:
        errors.append("requested increase exceeds the tier maximum")

    return {
        "valid": not errors,
        "errors": errors,
        "tier": tier,
        "requested_source": requested_source,
        "requested_increase_amount": requested_dollars,
        "maximum_whole_dollar_increase": maximum_whole_dollars,
        "maximum_increase_exact": format(raw_maximum, "f"),
        "prospective_new_credit_limit": format(limit + Decimal(requested_dollars), ".2f"),
        "account_age_days": age_days,
        "minimum_account_age_days": rules["minimum_age_days"],
        "account_age_passes": age_days >= rules["minimum_age_days"],
        "utilization_percent": format(utilization, ".6f"),
        "utilization_threshold_percent": format(rules["utilization_threshold_percent"], "f"),
        "utilization_passes": utilization < rules["utilization_threshold_percent"],
        "cooldown_days": rules["cooldown_days"],
        "required_payment_months": rules["payment_months"],
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        result = main(json.loads(raw))
    except json.JSONDecodeError:
        result = error_output("stdin must contain valid JSON")
    except Exception as exc:  # Keep the script's JSON output contract on unexpected input.
        result = error_output("unable to calculate CLI request: " + str(exc))
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
