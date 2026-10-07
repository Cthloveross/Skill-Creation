#!/usr/bin/env python3
"""Evaluate Rho-Bank provisional-credit rules from one JSON object on stdin."""
import json
import sys
from datetime import datetime

ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}
ALL_REASONS = ELIGIBLE_REASONS | {
    "incorrect_amount", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
LIMITS = {
    "Bronze Rewards Card": 2500.0, "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0, "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0, "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0, "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0, "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0, "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}


def date_value(data, field, errors):
    value = data.get(field)
    if not isinstance(value, str):
        errors.append(f"{field} must be a date string in MM/DD/YYYY format")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{field} must use MM/DD/YYYY format")
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"eligible_for_provisional_credit": False, "determinate": False,
                          "checks": {}, "errors": [f"invalid JSON: {exc}"]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"eligible_for_provisional_credit": False, "determinate": False,
                          "checks": {}, "errors": ["input must be a JSON object"]}))
        return

    errors = []
    reason = data.get("dispute_reason")
    if reason not in ALL_REASONS:
        errors.append("dispute_reason is not a permitted reason")

    # A permitted category outside this set is explicitly never eligible. This
    # conclusion needs no unrelated account/history facts.
    if reason in ALL_REASONS - ELIGIBLE_REASONS:
        print(json.dumps({
            "eligible_for_provisional_credit": False, "determinate": True,
            "card_limit": LIMITS.get(data.get("card_type")),
            "checks": {"eligible_reason": False}, "errors": []
        }, sort_keys=True))
        return

    opened = date_value(data, "account_open_date", errors)
    purchased = date_value(data, "purchase_date", errors)
    evaluated = date_value(data, "evaluation_date", errors)
    card_type = data.get("card_type")
    limit = LIMITS.get(card_type)
    if card_type not in LIMITS:
        errors.append("card_type is not a recognized provisional-credit tier")
    try:
        raw_amount = data.get("transaction_amount")
        if isinstance(raw_amount, bool):
            raise ValueError
        amount = float(raw_amount)
        if amount < 0:
            raise ValueError
    except (TypeError, ValueError):
        amount = None
        errors.append("transaction_amount must be a non-negative number")
    prior = data.get("prior_disputes_past_12_months")
    if not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        prior = None
        errors.append("prior_disputes_past_12_months must be a non-negative integer")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")

    checks = {
        "eligible_reason": reason in ELIGIBLE_REASONS,
        "account_open_at_least_60_days": (evaluated - opened).days >= 60 if opened and evaluated else None,
        "amount_at_least_25": amount >= 25.0 if amount is not None else None,
        "amount_within_card_limit": amount <= limit if amount is not None and limit is not None else None,
        "no_more_than_two_prior_disputes": prior <= 2 if prior is not None else None,
        "merchant_contact_requirement": True if reason == "unauthorized_fraudulent_charge" else contacted if isinstance(contacted, bool) else None,
        "goods_not_received_more_than_30_days": ((evaluated - purchased).days > 30 if purchased and evaluated else None)
            if reason == "goods_services_not_received" else True,
    }
    determinate = not errors and all(value is not None for value in checks.values())
    print(json.dumps({
        "eligible_for_provisional_credit": bool(determinate and all(checks.values())),
        "determinate": determinate, "card_limit": limit, "checks": checks,
        "errors": errors,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
