#!/usr/bin/env python3
"""Deterministic eligibility calculations for credit-card request workflows.

Read JSON from stdin. Input must contain mode "provisional" or "cli". Output is
JSON with checks, missing fields, and a decision only when the supplied facts are
complete. This script neither accesses banking systems nor performs actions.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CLI_RULES = {
    "entry": {"min_age_days": 120, "cooldown_days": 120, "utilization_lt": Decimal("0.70"), "max_increase_pct": Decimal("0.25")},
    "mid": {"min_age_days": 90, "cooldown_days": 90, "utilization_lt": Decimal("0.80"), "max_increase_pct": Decimal("0.50")},
    "premium": {"min_age_days": 60, "cooldown_days": 60, "utilization_lt": Decimal("0.90"), "max_increase_pct": Decimal("0.50")},
}
PROVISIONAL_CAPS = {
    "entry": Decimal("2500"), "mid": Decimal("5000"), "premium": Decimal("10000"),
    "elite": Decimal("15000"), "invitation": Decimal("25000"),
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date is missing")
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    raise ValueError("unsupported date format: " + value)


def decimal_value(value):
    if value is None or value == "":
        raise ValueError("number is missing")
    try:
        return Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        raise ValueError("invalid number")


def required(data, names):
    return [name for name in names if name not in data or data[name] is None or data[name] == ""]


def provisional(data):
    needed = ["tier", "account_open_date", "current_date", "purchase_date", "amount", "reason", "contacted_merchant", "prior_dispute_dates"]
    missing = required(data, needed)
    if missing:
        return {"mode": "provisional", "complete": False, "missing": missing, "eligible": None}
    try:
        tier = str(data["tier"]).lower()
        cap = PROVISIONAL_CAPS[tier]
        current = parse_date(data["current_date"])
        opened = parse_date(data["account_open_date"])
        purchase = parse_date(data["purchase_date"])
        amount = decimal_value(data["amount"])
        prior_dates = [parse_date(x) for x in data["prior_dispute_dates"]]
    except (KeyError, ValueError) as exc:
        return {"mode": "provisional", "complete": False, "missing": [], "error": str(exc), "eligible": None}

    reason = data["reason"]
    fraud = reason == "unauthorized_fraudulent_charge"
    qualifying_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    in_window = [d for d in prior_dates if 0 <= (current - d).days <= 365]
    checks = {
        "account_age_at_least_60_days": (current - opened).days >= 60,
        "qualifying_reason": qualifying_reason,
        "goods_not_received_more_than_30_days_old": reason != "goods_services_not_received" or (current - purchase).days > 30,
        "amount_at_least_25": amount >= Decimal("25"),
        "amount_within_tier_cap": amount <= cap,
        "no_more_than_two_prior_disputes_in_12_months": len(in_window) <= 2,
        "merchant_contact_for_nonfraud": fraud or data["contacted_merchant"] is True,
    }
    return {"mode": "provisional", "complete": True, "eligible": all(checks.values()), "checks": checks,
            "prior_disputes_in_12_months": len(in_window), "tier_cap": str(cap)}


def cli(data):
    needed = ["tier", "current_limit", "current_balance", "requested_increase", "account_open_date", "current_date", "has_active_disputes", "has_pending_replacement", "past_due_amount", "payment_history_on_time"]
    missing = required(data, needed)
    if missing:
        return {"mode": "cli", "complete": False, "missing": missing, "approve": None}
    try:
        tier = str(data["tier"]).lower()
        rules = CLI_RULES[tier]
        current_limit = decimal_value(data["current_limit"])
        balance = decimal_value(data["current_balance"])
        increase = decimal_value(data["requested_increase"])
        past_due = decimal_value(data["past_due_amount"])
        current = parse_date(data["current_date"])
        opened = parse_date(data["account_open_date"])
        last = data.get("last_approved_request_date")
        last_date = parse_date(last) if last not in (None, "") else None
        if current_limit <= 0:
            raise ValueError("current_limit must be positive")
    except (KeyError, ValueError) as exc:
        return {"mode": "cli", "complete": False, "missing": [], "error": str(exc), "approve": None}

    max_increase = current_limit * rules["max_increase_pct"]
    utilization = balance / current_limit
    cooldown_ok = last_date is None or (current - last_date).days >= rules["cooldown_days"]
    checks = {
        "requested_increase_positive": increase > 0,
        "requested_increase_within_limit": increase <= max_increase,
        "account_age_requirement": (current - opened).days >= rules["min_age_days"],
        "cooldown_elapsed": cooldown_ok,
        "no_active_disputes": data["has_active_disputes"] is False,
        "no_pending_replacement": data["has_pending_replacement"] is False,
        "no_past_due_balance": past_due <= 0,
        "utilization_strictly_below_threshold": utilization < rules["utilization_lt"],
        "required_payment_history_on_time": data["payment_history_on_time"] is True,
    }
    return {
        "mode": "cli", "complete": True, "approve": all(checks.values()), "checks": checks,
        "max_increase": str(max_increase), "new_credit_limit": str(current_limit + increase),
        "utilization_percent": str(utilization * Decimal("100")),
        "required_payment_months": 6 if tier == "entry" else 3,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        mode = data.get("mode")
        if mode == "provisional":
            result = provisional(data)
        elif mode == "cli":
            result = cli(data)
        else:
            result = {"complete": False, "error": "mode must be provisional or cli"}
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"complete": False, "error": str(exc)}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
