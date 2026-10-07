#!/usr/bin/env python3
"""Assess documented provisional-credit rules from a JSON object on stdin.

Input keys: current_date, account_open_date, purchase_date (ISO YYYY-MM-DD
or MM/DD/YYYY), transaction_amount (number), card_tier (entry|mid|premium|
elite|invitation), dispute_reason, contacted_merchant (bool), and
prior_disputes_last_12_months (nonnegative integer).
Output: JSON eligibility decision and explanatory failed_conditions. Invalid
input returns JSON with an error field and exits normally so callers can show
validation errors without treating missing facts as eligibility.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

CAPS = {
    "entry": Decimal("2500.00"),
    "mid": Decimal("5000.00"),
    "premium": Decimal("10000.00"),
    "elite": Decimal("15000.00"),
    "invitation": Decimal("25000.00"),
}
QUALIFYING = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date must use YYYY-MM-DD or MM/DD/YYYY")


def main(data):
    required = [
        "current_date", "account_open_date", "purchase_date",
        "transaction_amount", "card_tier", "dispute_reason",
        "contacted_merchant", "prior_disputes_last_12_months",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError("missing required keys: " + ", ".join(missing))
    current = parse_date(data["current_date"])
    opened = parse_date(data["account_open_date"])
    purchased = parse_date(data["purchase_date"])
    if opened > current or purchased > current:
        raise ValueError("account_open_date and purchase_date cannot be future dates")
    tier = str(data["card_tier"]).strip().lower()
    if tier not in CAPS:
        raise ValueError("card_tier must be one of: " + ", ".join(CAPS))
    if not isinstance(data["contacted_merchant"], bool):
        raise ValueError("contacted_merchant must be boolean")
    prior = data["prior_disputes_last_12_months"]
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        raise ValueError("prior_disputes_last_12_months must be a nonnegative integer")
    try:
        amount = Decimal(str(data["transaction_amount"]))
    except (InvalidOperation, ValueError):
        raise ValueError("transaction_amount must be numeric")
    if amount < 0:
        raise ValueError("transaction_amount cannot be negative")

    reason = data["dispute_reason"]
    account_age_days = (current - opened).days
    purchase_age_days = (current - purchased).days
    failed = []
    if account_age_days < 60:
        failed.append("account_open_less_than_60_days")
    if reason not in QUALIFYING:
        failed.append("dispute_reason_not_eligible")
    if amount < Decimal("25.00"):
        failed.append("transaction_amount_under_25")
    if amount > CAPS[tier]:
        failed.append("transaction_amount_exceeds_tier_cap")
    if prior > 2:
        failed.append("more_than_two_prior_disputes_in_12_months")
    if reason != "unauthorized_fraudulent_charge" and not data["contacted_merchant"]:
        failed.append("merchant_not_contacted_for_nonfraud_dispute")
    if reason == "goods_services_not_received" and purchase_age_days <= 30:
        failed.append("goods_not_received_purchase_not_more_than_30_days_old")
    return {
        "eligible_for_provisional_credit": not failed,
        "failed_conditions": failed,
        "tier": tier,
        "tier_maximum": float(CAPS[tier]),
        "account_age_days": account_age_days,
        "purchase_age_days": purchase_age_days,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
