#!/usr/bin/env python3
"""Assess deterministic credit-card eligibility facts from a JSON stdin object.

This helper performs no bank operations. It emits one JSON object to stdout.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

TIER = {
    "entry": {"age": 120, "cooldown": 120, "utilization": Decimal("70"),
              "max_increase_ratio": Decimal("0.25"), "payments": 6,
              "provisional_limit": Decimal("2500")},
    "mid": {"age": 90, "cooldown": 90, "utilization": Decimal("80"),
            "max_increase_ratio": Decimal("0.50"), "payments": 3,
            "provisional_limit": Decimal("5000")},
    "premium": {"age": 60, "cooldown": 60, "utilization": Decimal("90"),
                "max_increase_ratio": Decimal("0.50"), "payments": 3,
                "provisional_limit": Decimal("10000")},
}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use YYYY-MM-DD or MM/DD/YYYY")


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be numeric")
    if result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def require_bool(data, key):
    value = data.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean")
    return value


def main(data):
    required = [
        "today", "account_open_date", "tier", "balance", "credit_limit",
        "transaction_amount", "dispute_reason", "prior_disputes_12mo",
        "contacted_merchant", "cli_increase_amount", "consecutive_on_time_months",
        "pending_disputes", "pending_replacement", "past_due",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError("missing required keys: " + ", ".join(missing))

    tier_name = data["tier"]
    if tier_name not in TIER:
        raise ValueError("tier must be entry, mid, or premium")
    rules = TIER[tier_name]
    today = parse_date(data["today"], "today")
    opened = parse_date(data["account_open_date"], "account_open_date")
    if opened > today:
        raise ValueError("account_open_date cannot be in the future")
    account_age_days = (today - opened).days
    balance = money(data["balance"], "balance")
    limit = money(data["credit_limit"], "credit_limit")
    if limit <= 0:
        raise ValueError("credit_limit must be greater than zero")
    amount = money(data["transaction_amount"], "transaction_amount")
    increase = money(data["cli_increase_amount"], "cli_increase_amount")
    try:
        prior_disputes = int(data["prior_disputes_12mo"])
        on_time_months = int(data["consecutive_on_time_months"])
    except (ValueError, TypeError):
        raise ValueError("prior_disputes_12mo and consecutive_on_time_months must be integers")
    if prior_disputes < 0 or on_time_months < 0:
        raise ValueError("counts must not be negative")

    contacted = require_bool(data, "contacted_merchant")
    pending_disputes = require_bool(data, "pending_disputes")
    pending_replacement = require_bool(data, "pending_replacement")
    past_due = require_bool(data, "past_due")
    utilization = (balance / limit) * Decimal("100")

    provisional_reasons = []
    reason = data["dispute_reason"]
    allowed_reasons = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    if account_age_days < 60:
        provisional_reasons.append("account_under_60_days")
    if reason not in allowed_reasons:
        provisional_reasons.append("reason_not_eligible")
    if reason == "goods_services_not_received":
        if not data.get("purchase_date"):
            provisional_reasons.append("purchase_date_required")
        else:
            purchase = parse_date(data["purchase_date"], "purchase_date")
            if (today - purchase).days <= 30:
                provisional_reasons.append("goods_not_received_purchase_not_over_30_days")
    if amount < Decimal("25"):
        provisional_reasons.append("amount_under_25")
    if amount > rules["provisional_limit"]:
        provisional_reasons.append("amount_exceeds_tier_limit")
    if prior_disputes > 2:
        provisional_reasons.append("more_than_two_prior_disputes")
    if reason != "unauthorized_fraudulent_charge" and not contacted:
        provisional_reasons.append("merchant_not_contacted")

    cli_reasons = []
    max_increase = limit * rules["max_increase_ratio"]
    amount_valid = increase <= max_increase
    if not amount_valid:
        cli_reasons.append("requested_amount_exceeds_limit")
    if account_age_days < rules["age"]:
        cli_reasons.append("insufficient_account_age")
    last_approved = data.get("last_approved_cli_date")
    cooldown_days_since = None
    if last_approved not in (None, ""):
        approved_date = parse_date(last_approved, "last_approved_cli_date")
        if approved_date > today:
            raise ValueError("last_approved_cli_date cannot be in the future")
        cooldown_days_since = (today - approved_date).days
        if cooldown_days_since < rules["cooldown"]:
            cli_reasons.append("cooldown_period_active")
    if pending_disputes:
        cli_reasons.append("pending_disputes")
    if pending_replacement:
        cli_reasons.append("pending_replacement_card")
    if past_due:
        cli_reasons.append("past_due_balance")
    if utilization >= rules["utilization"]:
        cli_reasons.append("high_utilization")
    if on_time_months < rules["payments"]:
        cli_reasons.append("insufficient_payment_history")

    return {
        "errors": [],
        "account_age_days": account_age_days,
        "utilization_percent": str(utilization.quantize(Decimal("0.01"))),
        "provisional_credit": {
            "eligible": not provisional_reasons,
            "reasons": provisional_reasons,
            "tier_limit": str(rules["provisional_limit"]),
        },
        "cli": {
            "max_increase_amount": str(max_increase.quantize(Decimal("0.01"))),
            "requested_amount_valid": amount_valid,
            "cooldown_days_since_last_approved": cooldown_days_since,
            "eligible_after_submission_checks": not cli_reasons,
            "denial_reasons": cli_reasons,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": [str(exc)]}, separators=(",", ":"), sort_keys=True))
        sys.exit(2)
