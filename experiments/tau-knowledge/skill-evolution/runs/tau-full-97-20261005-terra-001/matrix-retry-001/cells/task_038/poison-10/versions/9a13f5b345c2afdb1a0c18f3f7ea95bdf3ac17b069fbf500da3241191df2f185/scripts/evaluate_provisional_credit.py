#!/usr/bin/env python3
"""Evaluate documented provisional-credit rules.

Reads one JSON object from stdin and writes one JSON object to stdout.
Required input:
  account_open_date, as_of_date, card_type, transaction_amount,
  purchase_date, dispute_reason, contacted_merchant,
  disputes_past_12_months.
Dates use MM/DD/YYYY. transaction_amount may be a JSON number or a numeric
string without a currency symbol. Output contains eligibility, explanations,
and computed account/purchase ages. Invalid input produces valid_input=false
and eligibility=false rather than guessing.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
TIER_LIMITS = {
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


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an MM/DD/YYYY string")
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{field} must be a real date in MM/DD/YYYY format")


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("transaction_amount must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("transaction_amount must be numeric")
    if not amount.is_finite() or amount < 0:
        raise ValueError("transaction_amount must be a nonnegative finite number")
    return amount


def evaluate(data):
    required = [
        "account_open_date", "as_of_date", "card_type", "transaction_amount",
        "purchase_date", "dispute_reason", "contacted_merchant",
        "disputes_past_12_months",
    ]
    missing = [key for key in required if key not in data]
    if missing:
        return {"valid_input": False, "eligible_for_provisional_credit": False,
                "errors": ["missing required fields: " + ", ".join(missing)]}
    try:
        opened = parse_date(data["account_open_date"], "account_open_date")
        as_of = parse_date(data["as_of_date"], "as_of_date")
        purchase = parse_date(data["purchase_date"], "purchase_date")
        amount = parse_amount(data["transaction_amount"])
        count = data["disputes_past_12_months"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("disputes_past_12_months must be a nonnegative integer")
        if not isinstance(data["contacted_merchant"], bool):
            raise ValueError("contacted_merchant must be boolean")
    except ValueError as exc:
        return {"valid_input": False, "eligible_for_provisional_credit": False,
                "errors": [str(exc)]}

    account_age_days = (as_of - opened).days
    purchase_age_days = (as_of - purchase).days
    reason = data["dispute_reason"]
    card_type = data["card_type"]
    reasons = []

    if account_age_days < 60:
        reasons.append("account has been open fewer than 60 days")
    if reason not in ELIGIBLE_REASONS:
        reasons.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received" and purchase_age_days <= 30:
        reasons.append("goods/services-not-received purchase is not more than 30 days old")
    limit = TIER_LIMITS.get(card_type)
    if limit is None:
        reasons.append("card type has no documented provisional-credit tier limit")
    else:
        if amount < Decimal("25.00"):
            reasons.append("transaction amount is under $25.00")
        if amount > limit:
            reasons.append("transaction amount exceeds the card tier limit")
    if count > 2:
        reasons.append("more than two disputes were filed in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and not data["contacted_merchant"]:
        reasons.append("merchant was not contacted for a non-fraud dispute")

    return {
        "valid_input": True,
        "eligible_for_provisional_credit": not reasons,
        "reasons": reasons,
        "account_age_days": account_age_days,
        "purchase_age_days": purchase_age_days,
        "transaction_amount": format(amount, ".2f"),
        "tier_limit": format(limit, ".2f") if limit is not None else None,
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        result = evaluate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"valid_input": False, "eligible_for_provisional_credit": False,
                  "errors": [str(exc)]}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
