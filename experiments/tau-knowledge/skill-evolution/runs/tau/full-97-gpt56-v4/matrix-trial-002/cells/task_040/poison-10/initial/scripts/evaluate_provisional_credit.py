#!/usr/bin/env python3
"""Evaluate Rho-Bank provisional-credit eligibility from JSON stdin.

Input and output schemas are documented in SKILL.md. This program performs no
bank action and deliberately returns ineligible for malformed/missing data.
"""
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

LIMITS = {
    "Bronze Rewards Card": Decimal("2500"),
    "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"),
    "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"),
    "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"),
    "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"),
    "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"),
    "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}
QUALIFYING_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
FRAUD = "unauthorized_fraudulent_charge"


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    value = value.strip()
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            return date.fromisoformat(value)


def as_money(value):
    if isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value))


def main(payload):
    failed = []
    try:
        filing = parse_date(payload.get("filing_date"))
        opened = parse_date(payload.get("account_open_date"))
        purchase = parse_date(payload.get("purchase_date"))
        amount = as_money(payload.get("amount"))
    except (ValueError, TypeError, InvalidOperation) as exc:
        return {"eligible": False, "failed_checks": ["invalid_or_missing_date_or_amount"], "detail": str(exc)}

    card_type = payload.get("card_type")
    limit = LIMITS.get(card_type)
    reason = payload.get("dispute_reason")
    contacted = payload.get("contacted_merchant")
    raw_history = payload.get("prior_dispute_dates")
    if not isinstance(raw_history, list):
        return {"eligible": False, "failed_checks": ["missing_prior_dispute_history"], "card_limit": str(limit) if limit else None}

    dates = []
    try:
        dates = [parse_date(x) for x in raw_history]
    except (ValueError, TypeError):
        return {"eligible": False, "failed_checks": ["invalid_prior_dispute_history"], "card_limit": str(limit) if limit else None}

    if filing < opened or (filing - opened).days < 60:
        failed.append("account_open_less_than_60_days")
    if reason not in QUALIFYING_REASONS:
        failed.append("dispute_reason_not_eligible")
    if reason == "goods_services_not_received" and (filing - purchase).days <= 30:
        failed.append("goods_not_received_purchase_not_more_than_30_days_old")
    if limit is None:
        failed.append("unknown_card_tier")
    elif amount < Decimal("25") or amount > limit:
        failed.append("amount_outside_eligible_range")
    # The trailing period begins one calendar year before filing, inclusive.
    trailing_count = sum(1 for d in dates if filing - timedelta(days=365) <= d <= filing)
    if trailing_count > 2:
        failed.append("more_than_two_prior_disputes_in_12_months")
    if reason != FRAUD and contacted is not True:
        failed.append("merchant_not_contacted_for_nonfraud_dispute")

    return {
        "eligible": not failed,
        "card_limit": str(limit) if limit is not None else None,
        "prior_disputes_in_last_12_months": trailing_count,
        "failed_checks": failed,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        result = main(data)
    except Exception as exc:
        result = {"eligible": False, "failed_checks": ["invalid_input"], "detail": str(exc)}
    print(json.dumps(result, sort_keys=True))
