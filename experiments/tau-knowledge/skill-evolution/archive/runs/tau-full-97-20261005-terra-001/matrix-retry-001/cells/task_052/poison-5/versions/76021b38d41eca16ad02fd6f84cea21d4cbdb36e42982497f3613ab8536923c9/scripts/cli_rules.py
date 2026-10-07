#!/usr/bin/env python3
"""Calculate deterministic CLI policy values.

Reads one JSON object from stdin and emits one JSON object.  This program is
pure: it does not call banking tools or read customer records.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry": {"min_age_days": 120, "cooldown_days": 120,
              "max_utilization_percent": Decimal("70"),
              "payment_months": 6, "max_increase_fraction": Decimal("0.25")},
    "mid": {"min_age_days": 90, "cooldown_days": 90,
            "max_utilization_percent": Decimal("80"),
            "payment_months": 3, "max_increase_fraction": Decimal("0.50")},
    "premium": {"min_age_days": 60, "cooldown_days": 60,
                "max_utilization_percent": Decimal("90"),
                "payment_months": 3, "max_increase_fraction": Decimal("0.50")},
}


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must use a valid YYYY-MM-DD date")


def money_string(amount):
    return format(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def main(data):
    errors = []
    if not isinstance(data, dict):
        return {"errors": ["input must be a JSON object"]}

    tier = data.get("tier")
    if not isinstance(tier, str):
        errors.append("tier must be entry, mid, or premium")
        rule = None
    else:
        rule = RULES.get(tier.strip().lower())
        if rule is None:
            errors.append("tier must be entry, mid, or premium")

    try:
        limit = decimal_value(data.get("current_limit"), "current_limit")
        if limit <= 0:
            errors.append("current_limit must be greater than zero")
    except ValueError as exc:
        errors.append(str(exc))
        limit = None
    try:
        balance = decimal_value(data.get("current_balance"), "current_balance")
        if balance < 0:
            errors.append("current_balance must not be negative")
    except ValueError as exc:
        errors.append(str(exc))
        balance = None
    try:
        opened = parse_date(data.get("account_open_date"), "account_open_date")
        as_of = parse_date(data.get("as_of_date"), "as_of_date")
        if opened > as_of:
            errors.append("account_open_date cannot be after as_of_date")
    except ValueError as exc:
        errors.append(str(exc))
        opened = as_of = None

    amount_given = data.get("requested_increase_amount") is not None
    percent_given = data.get("requested_percent") is not None
    if amount_given == percent_given:
        errors.append("provide exactly one of requested_increase_amount or requested_percent")
        requested = None
    else:
        try:
            if amount_given:
                requested = decimal_value(data["requested_increase_amount"], "requested_increase_amount")
            else:
                pct = decimal_value(data["requested_percent"], "requested_percent")
                if pct <= 0:
                    raise ValueError("requested_percent must be greater than zero")
                if limit is None:
                    raise ValueError("cannot calculate percentage request without a valid current_limit")
                requested = limit * pct / Decimal("100")
            if requested <= 0:
                errors.append("requested increase must be greater than zero")
            if requested != requested.to_integral_value():
                errors.append("requested increase must be an exact whole-dollar amount")
        except ValueError as exc:
            errors.append(str(exc))
            requested = None

    last_raw = data.get("last_approved_request_date")
    try:
        last_approved = None if last_raw is None else parse_date(last_raw, "last_approved_request_date")
        if last_approved is not None and as_of is not None and last_approved > as_of:
            errors.append("last_approved_request_date cannot be after as_of_date")
    except ValueError as exc:
        errors.append(str(exc))
        last_approved = None

    result = {"errors": errors}
    if rule:
        result["tier"] = tier.strip().lower()
        result["policy"] = {
            "minimum_account_age_days": rule["min_age_days"],
            "cooldown_days": rule["cooldown_days"],
            "maximum_utilization_percent": str(rule["max_utilization_percent"]),
            "required_on_time_payment_months": rule["payment_months"],
            "maximum_increase_fraction": str(rule["max_increase_fraction"]),
        }
    if rule and limit is not None and limit > 0:
        maximum = limit * rule["max_increase_fraction"]
        result["maximum_increase_amount"] = money_string(maximum)
        if requested is not None:
            result["requested_increase_amount"] = str(requested.to_integral_value())
            result["amount_valid"] = (requested > 0 and requested == requested.to_integral_value()
                                      and requested <= maximum)
    if rule and opened is not None and as_of is not None and opened <= as_of:
        age = (as_of - opened).days
        result["account_age_days"] = age
        result["account_age_eligible"] = age >= rule["min_age_days"]
    if rule and limit is not None and limit > 0 and balance is not None and balance >= 0:
        utilization = balance / limit * Decimal("100")
        result["utilization_percent"] = money_string(utilization)
        result["utilization_eligible"] = utilization < rule["max_utilization_percent"]
    if rule and as_of is not None:
        if last_approved is None:
            result["cooldown_eligible"] = True
            result["next_cooldown_eligible_date"] = None
        else:
            next_date = last_approved + timedelta(days=rule["cooldown_days"])
            result["cooldown_eligible"] = as_of >= next_date
            result["next_cooldown_eligible_date"] = next_date.isoformat()
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"invalid JSON input: {exc.msg}"]}, sort_keys=True))
    except Exception as exc:
        # Keep the JSON interface stable for the executor without exposing a traceback.
        print(json.dumps({"errors": [f"calculation failed: {exc}"]}, sort_keys=True))
