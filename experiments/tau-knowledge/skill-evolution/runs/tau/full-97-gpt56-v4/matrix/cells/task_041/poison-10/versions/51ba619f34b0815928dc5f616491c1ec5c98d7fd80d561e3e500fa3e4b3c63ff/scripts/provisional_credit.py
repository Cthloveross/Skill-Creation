#!/usr/bin/env python3
"""Evaluate credit-card provisional-credit eligibility.

Reads one JSON object from stdin and writes one JSON object to stdout.
Required input: today, account_open_date, card_type, transaction_amount,
purchase_date, dispute_reason, contacted_merchant, past_dispute_dates.
Dates use MM/DD/YYYY; past_dispute_dates is a list of such dates.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

DATE_FMT = "%m/%d/%Y"
LIMITS = {
    "Bronze Rewards Card": Decimal("2500.00"),
    "EcoCard": Decimal("2500.00"),
    "Business Bronze Rewards Card": Decimal("2500.00"),
    "Crypto-Cash Back Card": Decimal("2500.00"),
    "Silver Rewards Card": Decimal("5000.00"),
    "Business Silver Rewards Card": Decimal("5000.00"),
    "Green Rewards Card": Decimal("5000.00"),
    "Silver Zoom Card": Decimal("5000.00"),
    "Gold Rewards Card": Decimal("10000.00"),
    "Business Gold Rewards Card": Decimal("10000.00"),
    "Platinum Rewards Card": Decimal("15000.00"),
    "Business Platinum Rewards Card": Decimal("15000.00"),
    "Diamond Elite Card": Decimal("25000.00"),
}
ALLOWED_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
FRAUD = "unauthorized_fraudulent_charge"
NOT_RECEIVED = "goods_services_not_received"


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(field + " must be MM/DD/YYYY")
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        raise ValueError(field + " must be MM/DD/YYYY")


def main():
    try:
        data = json.load(sys.stdin)
        today = parse_date(data["today"], "today")
        opened = parse_date(data["account_open_date"], "account_open_date")
        purchased = parse_date(data["purchase_date"], "purchase_date")
        amount = Decimal(str(data["transaction_amount"]))
        if amount.is_nan() or amount.is_infinite():
            raise ValueError("transaction_amount must be finite")
        reason = data["dispute_reason"]
        contacted = data["contacted_merchant"]
        card_type = data["card_type"]
        history = data["past_dispute_dates"]
        if type(contacted) is not bool:
            raise ValueError("contacted_merchant must be boolean")
        if not isinstance(history, list):
            raise ValueError("past_dispute_dates must be a list")
        prior_dates = [parse_date(x, "past_dispute_dates entry") for x in history]
    except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
        print(json.dumps({"eligible_for_provisional_credit": False, "error": str(exc)}))
        return

    failures = []
    limit = LIMITS.get(card_type)
    if (today - opened).days < 60:
        failures.append("account_open_less_than_60_days")
    if reason not in ALLOWED_REASONS:
        failures.append("reason_not_eligible")
    if reason == NOT_RECEIVED and (today - purchased).days <= 30:
        failures.append("goods_not_received_purchase_not_more_than_30_days_ago")
    if amount < Decimal("25.00"):
        failures.append("amount_below_25")
    if limit is None:
        failures.append("unknown_card_tier")
    elif amount > limit:
        failures.append("amount_exceeds_tier_limit")
    # The preceding 12 months is inclusive of the boundary and excludes future dates.
    cutoff = date(today.year - 1, today.month, today.day)
    previous = sum(1 for d in prior_dates if cutoff <= d <= today)
    if previous > 2:
        failures.append("more_than_two_prior_disputes_in_12_months")
    if reason != FRAUD and not contacted:
        failures.append("merchant_not_contacted_for_non_fraud_dispute")

    result = {
        "eligible_for_provisional_credit": not failures,
        "failed_conditions": failures,
        "previous_disputes_in_last_12_months": previous,
        "maximum_provisional_credit_limit": str(limit) if limit is not None else None,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
