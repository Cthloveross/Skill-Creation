#!/usr/bin/env python3
"""Assess a submitted or proposed CLI from normalized runtime facts.

Reads JSON from stdin and emits JSON to stdout. Required keys:
as_of_date, account_open_date, card_tier, current_balance, current_credit_limit,
past_due_amount, requested_increase_amount, last_approved_request_date,
has_active_disputes, pending_order_statuses, consecutive_on_time_months.

last_approved_request_date may be null only when the CLI-history result confirms no
approved request establishes a cooldown. pending_order_statuses must contain all
currently returned replacement-order statuses, using an empty list when verified empty.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from policy import CLI_POLICY, decimal, json_decimal, parse_date, tier

FINAL_ORDER_STATUSES = {"delivered", "cancelled", "canceled"}
DENIAL_ORDER = [
    ("account_age", "insufficient_account_age"),
    ("cooldown", "cooldown_period_active"),
    ("active_disputes", "pending_disputes"),
    ("pending_replacement", "pending_replacement_card"),
    ("good_standing", "past_due_balance"),
    ("utilization", "high_utilization"),
    ("payment_history", "insufficient_payment_history"),
]

def main() -> None:
    try:
        data = json.load(sys.stdin)
        required = ["as_of_date", "account_open_date", "card_tier", "current_balance", "current_credit_limit", "past_due_amount", "requested_increase_amount", "last_approved_request_date", "has_active_disputes", "pending_order_statuses", "consecutive_on_time_months"]
        missing = [x for x in required if x not in data]
        if missing:
            raise ValueError("missing required fields: " + ", ".join(missing))
        card_tier = tier(data["card_tier"])
        if card_tier not in CLI_POLICY:
            raise ValueError("CLI policy is only defined for Entry, Mid, and Premium tiers")
        policy = CLI_POLICY[card_tier]
        as_of = parse_date(data["as_of_date"])
        opened = parse_date(data["account_open_date"])
        if opened > as_of:
            raise ValueError("account_open_date cannot be in the future")
        balance = decimal(data["current_balance"], "current_balance")
        limit = decimal(data["current_credit_limit"], "current_credit_limit")
        past_due = decimal(data["past_due_amount"], "past_due_amount")
        requested = decimal(data["requested_increase_amount"], "requested_increase_amount")
        if limit <= 0:
            raise ValueError("current_credit_limit must be greater than zero")
        if balance < 0 or past_due < 0:
            raise ValueError("balance and past_due_amount cannot be negative")
        if not isinstance(data["has_active_disputes"], bool):
            raise ValueError("has_active_disputes must be boolean")
        statuses = data["pending_order_statuses"]
        if not isinstance(statuses, list) or not all(isinstance(x, str) for x in statuses):
            raise ValueError("pending_order_statuses must be a list of strings")
        months = int(data["consecutive_on_time_months"])
        if months < 0:
            raise ValueError("consecutive_on_time_months cannot be negative")

        age_days = (as_of - opened).days
        cooldown_ok = True
        cooldown_days_elapsed = None
        anchor = data["last_approved_request_date"]
        if anchor is not None:
            anchor_date = parse_date(anchor)
            if anchor_date > as_of:
                raise ValueError("last_approved_request_date cannot be in the future")
            cooldown_days_elapsed = (as_of - anchor_date).days
            cooldown_ok = cooldown_days_elapsed >= policy["cooldown_days"]
        maximum = limit * policy["increase_pct"] / Decimal("100")
        utilization = balance * Decimal("100") / limit
        pending = any(status.strip().lower() not in FINAL_ORDER_STATUSES for status in statuses)
        criteria = {
            "account_age": age_days >= policy["age_days"],
            "cooldown": cooldown_ok,
            "active_disputes": not data["has_active_disputes"],
            "pending_replacement": not pending,
            "good_standing": past_due == 0,
            "utilization": utilization < policy["utilization_pct"],
            "payment_history": months >= policy["payment_months"],
        }
        valid_amount = requested > 0 and requested <= maximum
        denial_reason = next((reason for criterion, reason in DENIAL_ORDER if not criteria[criterion]), None)
        output = {
            "can_submit": valid_amount,
            "can_approve": valid_amount and all(criteria.values()),
            "amount_status": {
                "valid": valid_amount,
                "maximum_increase": json_decimal(maximum),
                "requested_increase": json_decimal(requested),
                "proposed_new_credit_limit": json_decimal(limit + requested),
            },
            "criteria": criteria,
            "denial_reason_after_submission": denial_reason,
            "derived": {
                "account_age_days": age_days,
                "cooldown_days_elapsed": cooldown_days_elapsed,
                "required_cooldown_days": policy["cooldown_days"],
                "utilization_percent": json_decimal(utilization),
                "maximum_utilization_percent_exclusive": json_decimal(policy["utilization_pct"]),
                "required_on_time_months": policy["payment_months"],
                "nonfinal_replacement_statuses": [s for s in statuses if s.strip().lower() not in FINAL_ORDER_STATUSES],
            },
        }
    except Exception as exc:
        output = {"error": str(exc), "can_submit": False, "can_approve": False}
    print(json.dumps(output, sort_keys=True))

if __name__ == "__main__":
    main()
