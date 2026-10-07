#!/usr/bin/env python3
"""Deterministically evaluate normalized CLI eligibility facts.

Reads one JSON object on stdin and writes one JSON object on stdout.  This
program does not contact banking systems and does not make a decision record.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

POLICY = {
    "entry-tier": {"age": 120, "cooldown": 120, "utilization": Decimal("70"), "payments": 6, "max_fraction": Decimal("0.25")},
    "mid-tier": {"age": 90, "cooldown": 90, "utilization": Decimal("80"), "payments": 3, "max_fraction": Decimal("0.50")},
    "premium-tier": {"age": 60, "cooldown": 60, "utilization": Decimal("90"), "payments": 3, "max_fraction": Decimal("0.50")},
}


def money(value):
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError("money must be finite")
    return value.quantize(Decimal("0.01"))


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an ISO YYYY-MM-DD date")


def fmt(value):
    return format(value.quantize(Decimal("0.01")), "f")


def invalid(message):
    return {"valid_input": False, "error": message}


def main(data):
    if not isinstance(data, dict):
        return invalid("input must be a JSON object")
    tier = data.get("tier")
    if tier not in POLICY:
        return invalid("tier must be entry-tier, mid-tier, or premium-tier")
    try:
        p = POLICY[tier]
        as_of = parse_date(data.get("as_of_date"), "as_of_date")
        opened = parse_date(data.get("account_open_date"), "account_open_date")
        if opened > as_of:
            raise ValueError("account_open_date cannot be after as_of_date")
        limit = money(data.get("current_credit_limit"))
        balance = money(data.get("current_balance"))
        past_due = money(data.get("past_due_amount"))
        requested_raw = data.get("requested_increase_amount")
        # bool is an int subclass but is never a valid dollar request.
        if isinstance(requested_raw, bool) or int(requested_raw) != requested_raw:
            raise ValueError("requested_increase_amount must be a whole-dollar integer")
        requested = Decimal(int(requested_raw))
        months = int(data.get("consecutive_on_time_months"))
    except (ValueError, TypeError, InvalidOperation) as exc:
        return invalid(str(exc))

    if limit <= 0:
        return invalid("current_credit_limit must be positive")
    if balance < 0 or past_due < 0:
        return invalid("balances cannot be negative")
    if requested <= 0:
        return invalid("requested_increase_amount must be positive")
    if months < 0:
        return invalid("consecutive_on_time_months cannot be negative")

    max_increase = (limit * p["max_fraction"]).quantize(Decimal("0.01"))
    age_days = (as_of - opened).days
    utilization = (balance / limit) * Decimal("100")

    recent = data.get("most_recent_approved_request_date")
    cooldown_ok = True
    next_eligible = None
    if recent is not None:
        try:
            recent_date = parse_date(recent, "most_recent_approved_request_date")
            if recent_date > as_of:
                raise ValueError("most_recent_approved_request_date cannot be after as_of_date")
        except ValueError as exc:
            return invalid(str(exc))
        next_eligible = recent_date + timedelta(days=p["cooldown"])
        cooldown_ok = as_of >= next_eligible

    required_booleans = ["has_active_disputes", "has_nonfinal_replacement_order", "account_current"]
    if any(not isinstance(data.get(key), bool) for key in required_booleans):
        return invalid("dispute, replacement-order, and account-current fields must be booleans")

    checks = {
        "account_age": age_days >= p["age"],
        "cooldown": cooldown_ok,
        "no_active_disputes": not data["has_active_disputes"],
        "no_nonfinal_replacement_order": not data["has_nonfinal_replacement_order"],
        "good_standing": data["account_current"] and past_due == 0,
        "utilization_below_threshold": utilization < p["utilization"],
        "payment_history": months >= p["payments"],
    }
    amount_ok = requested <= max_increase
    all_eligible = amount_ok and all(checks.values())

    reason = None
    if not checks["account_age"]:
        reason = "insufficient_account_age"
    elif not checks["cooldown"]:
        reason = "cooldown_period_active"
    elif not checks["no_active_disputes"]:
        reason = "pending_disputes"
    elif not checks["no_nonfinal_replacement_order"]:
        reason = "pending_replacement_card"
    elif not checks["good_standing"]:
        reason = "past_due_balance"
    elif not checks["utilization_below_threshold"]:
        reason = "high_utilization"
    elif not checks["payment_history"]:
        reason = "insufficient_payment_history"

    return {
        "valid_input": True,
        "tier": tier,
        "age_days": age_days,
        "maximum_increase": fmt(max_increase),
        "requested_increase_amount": str(int(requested)),
        "amount_within_limit": amount_ok,
        "new_credit_limit": fmt(limit + requested),
        "utilization_percent": str(utilization.quantize(Decimal("0.01"))),
        "utilization_must_be_below_percent": str(p["utilization"]),
        "required_on_time_months": p["payments"],
        "checks": checks,
        "next_eligible_date": next_eligible.isoformat() if next_eligible else None,
        "all_eligible": all_eligible,
        "recommended_denial_reason": reason,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps(invalid(f"invalid JSON: {exc.msg}"), sort_keys=True))
    except Exception as exc:  # ensure a machine-readable result for bad input
        print(json.dumps(invalid(str(exc)), sort_keys=True))
