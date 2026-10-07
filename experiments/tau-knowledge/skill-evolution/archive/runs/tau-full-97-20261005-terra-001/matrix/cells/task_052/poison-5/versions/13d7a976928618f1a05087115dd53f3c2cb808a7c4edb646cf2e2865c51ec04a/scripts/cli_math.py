#!/usr/bin/env python3
"""Validate and calculate tier-based CLI request math.

Reads one JSON object on stdin and always writes one JSON object on stdout.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN

RULES = {
    "entry": {
        "minimum_age_days": 120,
        "cooldown_days": 120,
        "utilization_threshold_percent": Decimal("70"),
        "max_increase_fraction": Decimal("0.25"),
        "payment_months": 6,
    },
    "mid": {
        "minimum_age_days": 90,
        "cooldown_days": 90,
        "utilization_threshold_percent": Decimal("80"),
        "max_increase_fraction": Decimal("0.50"),
        "payment_months": 3,
    },
    "premium": {
        "minimum_age_days": 60,
        "cooldown_days": 60,
        "utilization_threshold_percent": Decimal("90"),
        "max_increase_fraction": Decimal("0.50"),
        "payment_months": 3,
    },
}


def error_output(message):
    return {"valid": False, "errors": [message]}


def parse_money(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(field + " must be a numeric amount")
    cleaned = str(value).strip().replace("$", "").replace(",", "")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(field + " must be a numeric amount") from exc
    if not result.is_finite():
        raise ValueError(field + " must be finite")
    return result


def parse_date(value, field):
    text = str(value).strip()
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


def whole_dollars(amount, field):
    if amount != amount.to_integral_value():
        raise ValueError(field + " must be a whole-dollar amount")
    return int(amount)


def main(payload):
    if not isinstance(payload, dict):
        return error_output("input must be a JSON object")

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
        current_date = parse_date(payload.get("current_time"), "current_time")
        if opened > current_date:
            raise ValueError("account_open_date cannot be after current_time")
    except ValueError as exc:
        return error_output(str(exc))

    has_amount = payload.get("requested_increase_amount") is not None
    has_percent = payload.get("requested_percent") is not None
    if has_amount == has_percent:
        return error_output("provide exactly one of requested_increase_amount or requested_percent")

    try:
        if has_amount:
            requested = parse_money(
                payload["requested_increase_amount"], "requested_increase_amount"
            )
            source = "dollar_amount"
        else:
            percent = parse_money(payload["requested_percent"], "requested_percent")
            if percent <= 0:
                raise ValueError("requested_percent must be greater than zero")
            requested = limit * percent / Decimal("100")
            source = "percent"
        requested_dollars = whole_dollars(requested, "requested increase")
        if requested_dollars <= 0:
            raise ValueError("requested increase must be greater than zero")
    except ValueError as exc:
        return error_output(str(exc))

    exact_maximum = limit * rules["max_increase_fraction"]
    maximum_dollars = int(exact_maximum.to_integral_value(rounding=ROUND_DOWN))
    age_days = (current_date - opened).days
    utilization = balance * Decimal("100") / limit
    errors = []
    if requested_dollars > maximum_dollars:
        errors.append("requested increase exceeds the tier maximum")

    return {
        "valid": not errors,
        "errors": errors,
        "tier": tier,
        "requested_source": source,
        "requested_increase_amount": requested_dollars,
        "maximum_whole_dollar_increase": maximum_dollars,
        "maximum_increase_exact": format(exact_maximum, "f"),
        "prospective_new_credit_limit": format(limit + Decimal(requested_dollars), ".2f"),
        "account_age_days": age_days,
        "minimum_account_age_days": rules["minimum_age_days"],
        "account_age_passes": age_days >= rules["minimum_age_days"],
        "utilization_percent": format(utilization, ".6f"),
        "utilization_threshold_percent": format(
            rules["utilization_threshold_percent"], "f"
        ),
        "utilization_passes": utilization < rules["utilization_threshold_percent"],
        "cooldown_days": rules["cooldown_days"],
        "required_payment_months": rules["payment_months"],
    }


if __name__ == "__main__":
    try:
        result = main(json.loads(sys.stdin.read()))
    except json.JSONDecodeError:
        result = error_output("stdin must contain valid JSON")
    except Exception as exc:
        result = error_output("unable to calculate CLI request: " + str(exc))
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
