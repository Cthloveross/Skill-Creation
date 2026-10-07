#!/usr/bin/env python3
"""Evaluate Rho-Bank provisional-credit criteria from one JSON stdin object.

Writes {"eligible": bool, "failed_conditions": [str], "maximum_limit": number}
to stdout. Invalid inputs produce {"error": "..."} and a nonzero exit status.
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
REQUIRED = {
    "account_open_date", "reference_date", "purchase_date", "dispute_reason",
    "transaction_amount", "card_type", "prior_disputes_last_12_months",
    "contacted_merchant",
}


def date_value(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an MM/DD/YYYY string")
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError as exc:
        raise ValueError(f"{field} must use MM/DD/YYYY") from exc


def decimal_value(value):
    if isinstance(value, bool):
        raise ValueError("transaction_amount must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("transaction_amount must be numeric") from exc
    if not amount.is_finite():
        raise ValueError("transaction_amount must be finite")
    return amount


def evaluate(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    missing = sorted(REQUIRED - data.keys())
    if missing:
        raise ValueError("missing required fields: " + ", ".join(missing))

    opened = date_value(data["account_open_date"], "account_open_date")
    reference = date_value(data["reference_date"], "reference_date")
    purchase = date_value(data["purchase_date"], "purchase_date")
    if opened > reference:
        raise ValueError("account_open_date cannot be after reference_date")
    if purchase > reference:
        raise ValueError("purchase_date cannot be after reference_date")
    if not isinstance(data["contacted_merchant"], bool):
        raise ValueError("contacted_merchant must be boolean")
    prior = data["prior_disputes_last_12_months"]
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        raise ValueError("prior_disputes_last_12_months must be a nonnegative integer")
    card_type = data["card_type"]
    if card_type not in LIMITS:
        raise ValueError("unsupported card_type; supply an exact known card type")

    amount = decimal_value(data["transaction_amount"])
    reason = data["dispute_reason"]
    limit = LIMITS[card_type]
    failed = []
    if (reference - opened).days < 60:
        failed.append("account_open_less_than_60_days")
    if reason not in ELIGIBLE_REASONS:
        failed.append("reason_not_eligible")
    if reason == "goods_services_not_received" and (reference - purchase).days <= 30:
        failed.append("goods_not_received_purchase_not_more_than_30_days_old")
    if amount < Decimal("25"):
        failed.append("transaction_amount_under_25")
    if amount > limit:
        failed.append("transaction_amount_exceeds_card_limit")
    if prior > 2:
        failed.append("more_than_two_prior_disputes_in_12_months")
    if reason != "unauthorized_fraudulent_charge" and not data["contacted_merchant"]:
        failed.append("merchant_not_contacted_for_nonfraud_dispute")
    return {
        "eligible": not failed,
        "failed_conditions": failed,
        "maximum_limit": float(limit),
    }


def main():
    try:
        data = json.load(sys.stdin)
        print(json.dumps(evaluate(data), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
