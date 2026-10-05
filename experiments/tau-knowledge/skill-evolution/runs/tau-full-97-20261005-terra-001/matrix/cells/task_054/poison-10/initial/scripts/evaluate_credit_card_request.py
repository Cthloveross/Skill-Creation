#!/usr/bin/env python3
"""Deterministically evaluate normalized CLI and provisional-credit prerequisites.

Input JSON schema:
{
  "now": ISO/date string,
  "account": {"tier": "entry|mid|premium|elite|invitation", "opened_on": date,
              "credit_limit": number, "current_balance": number,
              "past_due_amount": number, "status": string},
  "cli": {"requested_increase": number, "approved_request_dates": [date],
          "has_active_dispute": bool, "has_pending_replacement": bool,
          "on_time_months": integer},
  "dispute": {"amount": number, "reason": string, "purchase_date": date,
              "contacted_merchant": bool, "disputes_last_12_months": integer}
}
Dates in approved_request_dates must already be filtered to approved CLI requests.
Output contains calculations, boolean checks, and a suggested denial reason. It does not
make banking calls and does not decide whether data from a tool is authoritative.
"""
import json
import sys
from datetime import datetime, date

CLI = {
    "entry": {"age": 120, "cooldown": 120, "util": 70.0, "months": 6, "fraction": 0.25},
    "mid": {"age": 90, "cooldown": 90, "util": 80.0, "months": 3, "fraction": 0.50},
    "premium": {"age": 60, "cooldown": 60, "util": 90.0, "months": 3, "fraction": 0.50},
}
PROVISIONAL_LIMIT = {"entry": 2500.0, "mid": 5000.0, "premium": 10000.0,
                     "elite": 15000.0, "invitation": 25000.0}

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    # Supports common ISO strings with a trailing Z.
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("unsupported date: " + value) from exc

def require_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(label + " must be a number")
    return float(value)

def main(payload):
    now = parse_date(payload["now"])
    account = payload["account"]
    cli = payload["cli"]
    dispute = payload["dispute"]
    tier = str(account["tier"]).lower().strip()
    if tier not in CLI:
        raise ValueError("CLI tier must be entry, mid, or premium")
    if tier not in PROVISIONAL_LIMIT:
        raise ValueError("unsupported provisional-credit tier")

    rules = CLI[tier]
    opened = parse_date(account["opened_on"])
    limit = require_number(account["credit_limit"], "credit_limit")
    balance = require_number(account["current_balance"], "current_balance")
    past_due = require_number(account["past_due_amount"], "past_due_amount")
    requested = require_number(cli["requested_increase"], "requested_increase")
    if limit <= 0:
        raise ValueError("credit_limit must be greater than zero")
    age_days = (now - opened).days
    utilization = balance / limit * 100.0
    approved_dates = [parse_date(x) for x in cli.get("approved_request_dates", [])]
    most_recent = max(approved_dates) if approved_dates else None
    cooldown_days = (now - most_recent).days if most_recent else None
    status = str(account.get("status", "")).upper()

    checks = {
        "account_age": age_days >= rules["age"],
        "cooldown": most_recent is None or cooldown_days >= rules["cooldown"],
        "no_active_dispute": not bool(cli.get("has_active_dispute", False)),
        "no_pending_replacement": not bool(cli.get("has_pending_replacement", False)),
        "good_standing": past_due <= 0 and status in {"ACTIVE", "CURRENT"},
        "utilization_below_threshold": utilization < rules["util"],
        "payment_history": int(cli.get("on_time_months", 0)) >= rules["months"],
    }
    amount_valid = requested > 0 and requested <= limit * rules["fraction"]
    failure_order = [
        ("account_age", "insufficient_account_age"),
        ("cooldown", "cooldown_period_active"),
        ("no_active_dispute", "pending_disputes"),
        ("no_pending_replacement", "pending_replacement_card"),
        ("good_standing", "past_due_balance"),
        ("utilization_below_threshold", "high_utilization"),
        ("payment_history", "insufficient_payment_history"),
    ]
    denial_reason = "requested_amount_exceeds_limit" if not amount_valid else None
    if amount_valid:
        for key, reason in failure_order:
            if not checks[key]:
                denial_reason = reason
                break

    amount = require_number(dispute["amount"], "dispute.amount")
    reason = str(dispute["reason"])
    purchase_age = (now - parse_date(dispute["purchase_date"])).days
    allowed_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
    if reason == "goods_services_not_received":
        allowed_reason = purchase_age > 30
    merchant_ok = reason == "unauthorized_fraudulent_charge" or bool(dispute.get("contacted_merchant", False))
    provisional_checks = {
        "account_age_at_least_60_days": age_days >= 60,
        "eligible_reason_and_delivery_age": allowed_reason,
        "amount_in_range": amount >= 25.0 and amount <= PROVISIONAL_LIMIT[tier],
        "no_more_than_two_prior_disputes": int(dispute.get("disputes_last_12_months", 0)) <= 2,
        "merchant_contact_when_required": merchant_ok,
    }
    return {
        "cli": {
            "tier": tier,
            "account_age_days": age_days,
            "utilization_percent": round(utilization, 6),
            "max_increase": round(limit * rules["fraction"], 2),
            "amount_valid_before_submission": amount_valid,
            "new_credit_limit_if_approved": round(limit + requested, 2),
            "most_recent_approved_request_date": most_recent.isoformat() if most_recent else None,
            "days_since_most_recent_approved_request": cooldown_days,
            "checks": checks,
            "eligible_for_approval": amount_valid and all(checks.values()),
            "suggested_denial_reason": denial_reason,
        },
        "dispute": {
            "purchase_age_days": purchase_age,
            "provisional_credit_limit": PROVISIONAL_LIMIT[tier],
            "provisional_credit_checks": provisional_checks,
            "eligible_for_provisional_credit": all(provisional_checks.values()),
        },
    }

if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
