#!/usr/bin/env python3
"""Deterministic CLI policy evaluator.

Reads one JSON object from stdin and writes one JSON object to stdout.  It has no
banking side effects. Dates may be ISO YYYY-MM-DD (including timestamps beginning with that date) or
MM/DD/YYYY, matching common account-record output. Amounts may be JSON numbers
or decimal strings.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RULES = {
    "entry-tier": {"age_days": 120, "cooldown_days": 120, "utilization_below": Decimal("70"), "payment_months": 6, "max_fraction": Decimal("0.25")},
    "mid-tier": {"age_days": 90, "cooldown_days": 90, "utilization_below": Decimal("80"), "payment_months": 3, "max_fraction": Decimal("0.50")},
    "premium-tier": {"age_days": 60, "cooldown_days": 60, "utilization_below": Decimal("90"), "payment_months": 3, "max_fraction": Decimal("0.50")},
}
ALIASES = {
    "entry": "entry-tier", "entry-tier": "entry-tier",
    "mid": "mid-tier", "mid-tier": "mid-tier",
    "premium": "premium-tier", "premium-tier": "premium-tier",
}
CENT = Decimal("0.01")


def out(obj):
    print(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str))


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    value = value.strip()
    if len(value) < 10:
        raise ValueError(f"{field} must be an ISO YYYY-MM-DD or MM/DD/YYYY date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        try:
            month, day, year = value[:10].split("/")
            return date(int(year), int(month), int(day))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{field} must be an ISO YYYY-MM-DD or MM/DD/YYYY date") from exc


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal amount") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def state_from_flag(value, true_means_failure=True):
    if value is None:
        return "unknown"
    if not isinstance(value, bool):
        return "unknown"
    failed = value if true_means_failure else not value
    return "fail" if failed else "pass"


def main(data):
    errors = []
    raw_tier = data.get("tier")
    tier = ALIASES.get(str(raw_tier).strip().lower()) if raw_tier is not None else None
    if tier is None:
        errors.append("tier must be Entry-tier, Mid-tier, or Premium-tier")
    try:
        as_of = parse_date(data.get("as_of_date"), "as_of_date")
        opened = parse_date(data.get("account_open_date"), "account_open_date")
        if opened > as_of:
            errors.append("account_open_date cannot be after as_of_date")
    except ValueError as exc:
        errors.append(str(exc))
        as_of = opened = None
    try:
        limit = money(data.get("current_credit_limit"), "current_credit_limit")
        balance = money(data.get("current_balance"), "current_balance")
        request = money(data.get("requested_increase_amount"), "requested_increase_amount")
        if limit <= 0:
            errors.append("current_credit_limit must be greater than zero")
        if balance < 0:
            errors.append("current_balance cannot be negative")
        if request <= 0:
            errors.append("requested_increase_amount must be greater than zero")
    except ValueError as exc:
        errors.append(str(exc))
        limit = balance = request = None

    prior = data.get("last_approved_request_date")
    prior_date = None
    if prior is not None:
        try:
            prior_date = parse_date(prior, "last_approved_request_date")
            if as_of and prior_date > as_of:
                errors.append("last_approved_request_date cannot be after as_of_date")
        except ValueError as exc:
            errors.append(str(exc))

    if errors:
        return {"recommendation": "invalid_input", "errors": errors}

    rule = RULES[tier]
    age_days = (as_of - opened).days
    max_increase = (limit * rule["max_fraction"]).quantize(CENT, rounding=ROUND_HALF_UP)
    utilization = ((balance / limit) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    criteria = {}
    criteria["account_age"] = {
        "state": "pass" if age_days >= rule["age_days"] else "fail",
        "actual_days": age_days,
        "required_days": rule["age_days"],
    }
    if prior_date is None:
        criteria["cooldown"] = {"state": "pass", "last_approved_request_date": None, "eligible_on": None}
    else:
        eligible_on = prior_date + timedelta(days=rule["cooldown_days"])
        criteria["cooldown"] = {
            "state": "pass" if as_of >= eligible_on else "fail",
            "last_approved_request_date": prior_date.isoformat(),
            "eligible_on": eligible_on.isoformat(),
            "required_full_days": rule["cooldown_days"],
        }
    criteria["utilization"] = {
        "state": "pass" if utilization < rule["utilization_below"] else "fail",
        "actual_percent": str(utilization),
        "must_be_below_percent": str(rule["utilization_below"]),
    }

    months = data.get("payment_on_time_consecutive_months")
    if months is None or isinstance(months, bool) or not isinstance(months, int) or months < 0:
        pay_state = "unknown"
    else:
        pay_state = "pass" if months >= rule["payment_months"] else "fail"
    criteria["payment_history"] = {"state": pay_state, "consecutive_on_time_months": months, "required_months": rule["payment_months"]}
    criteria["active_disputes"] = {"state": state_from_flag(data.get("has_active_disputes"))}
    criteria["pending_replacement_card"] = {"state": state_from_flag(data.get("has_pending_replacement_card"))}
    criteria["past_due_balance"] = {"state": state_from_flag(data.get("has_past_due_balance"))}

    amount_state = "pass" if request <= max_increase else "fail"
    criteria["requested_amount"] = {"state": amount_state, "requested_increase_amount": str(request), "maximum_increase_amount": str(max_increase)}

    result = {
        "tier": tier,
        "thresholds": {
            "minimum_account_age_days": rule["age_days"],
            "cooldown_days": rule["cooldown_days"],
            "utilization_must_be_below_percent": str(rule["utilization_below"]),
            "required_on_time_months": rule["payment_months"],
            "maximum_increase_fraction": str(rule["max_fraction"]),
        },
        "calculations": {
            "current_credit_limit": str(limit),
            "current_balance": str(balance),
            "current_utilization_percent": str(utilization),
            "maximum_increase_amount": str(max_increase),
            "proposed_new_credit_limit": str((limit + request).quantize(CENT)),
        },
        "criteria": criteria,
    }

    if amount_state == "fail":
        result.update({"recommendation": "amount_requires_customer_adjustment", "denial_reason": None})
        return result

    priority = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("active_disputes", "pending_disputes"),
        ("pending_replacement_card", "pending_replacement_card"),
        ("past_due_balance", "past_due_balance"),
        ("utilization", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    failures = [reason for key, reason in priority if criteria[key]["state"] == "fail"]
    unknowns = [key for key, _ in priority if criteria[key]["state"] == "unknown"]
    if failures:
        result.update({"recommendation": "deny", "denial_reason": failures[0], "all_failure_reasons": failures})
    elif unknowns:
        result.update({"recommendation": "hold_for_verification", "unknown_checks": unknowns, "denial_reason": None})
    else:
        result.update({"recommendation": "approve", "denial_reason": None})
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        out(main(payload))
    except Exception as exc:
        out({"recommendation": "invalid_input", "errors": [str(exc)]})
