#!/usr/bin/env python3
"""Evaluate documented provisional-credit criteria from JSON stdin."""
import json
import sys
from datetime import datetime, date

ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
LIMITS = {
    "Bronze Rewards Card": 2500.0,
    "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0,
    "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0,
    "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0,
    "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0,
    "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0,
    "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}


def parse_date(value, label, errors):
    if not isinstance(value, str):
        errors.append(f"{label} must be a date string in MM/DD/YYYY format")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{label} must use MM/DD/YYYY format")
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"eligible_for_provisional_credit": False, "determinate": False,
                          "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    errors = []
    opened = parse_date(data.get("account_open_date"), "account_open_date", errors)
    purchased = parse_date(data.get("purchase_date"), "purchase_date", errors)
    evaluated = parse_date(data.get("evaluation_date"), "evaluation_date", errors)
    reason = data.get("dispute_reason")
    card_type = data.get("card_type")

    try:
        amount = float(data.get("transaction_amount"))
        if amount < 0:
            raise ValueError
    except (TypeError, ValueError):
        amount = None
        errors.append("transaction_amount must be a non-negative number")

    prior = data.get("prior_disputes_past_12_months")
    if not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        errors.append("prior_disputes_past_12_months must be a non-negative integer")
        prior = None
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")

    if reason not in ELIGIBLE_REASONS and reason not in {
        "incorrect_amount", "goods_services_not_as_described",
        "canceled_subscription_still_charging", "refund_never_processed"
    }:
        errors.append("dispute_reason is not a permitted reason")
    if card_type not in LIMITS:
        errors.append("card_type is not a recognized provisional-credit tier")

    checks = {}
    checks["account_open_at_least_60_days"] = (
        (evaluated - opened).days >= 60 if opened and evaluated else None
    )
    checks["eligible_reason"] = reason in ELIGIBLE_REASONS if reason else None
    checks["goods_not_received_more_than_30_days"] = (
        (evaluated - purchased).days > 30 if reason == "goods_services_not_received" and purchased and evaluated
        else (True if reason != "goods_services_not_received" and reason else None)
    )
    limit = LIMITS.get(card_type)
    checks["amount_at_least_25"] = amount >= 25.0 if amount is not None else None
    checks["amount_within_card_limit"] = amount <= limit if amount is not None and limit is not None else None
    checks["no_more_than_two_prior_disputes"] = prior <= 2 if prior is not None else None
    checks["merchant_contact_requirement"] = (
        True if reason == "unauthorized_fraudulent_charge"
        else contacted if isinstance(contacted, bool) else None
    )

    determinate = not errors and all(value is not None for value in checks.values())
    eligible = determinate and all(checks.values())
    print(json.dumps({
        "eligible_for_provisional_credit": eligible,
        "determinate": determinate,
        "card_limit": limit,
        "checks": checks,
        "errors": errors,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
