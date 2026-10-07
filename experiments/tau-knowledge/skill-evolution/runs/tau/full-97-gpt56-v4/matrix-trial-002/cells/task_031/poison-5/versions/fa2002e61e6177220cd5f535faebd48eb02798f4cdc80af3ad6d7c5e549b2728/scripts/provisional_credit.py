#!/usr/bin/env python3
"""Calculate provisional-credit eligibility from a runtime JSON input object.

Reads one JSON object from stdin and writes one JSON object to stdout.  Input:
{
  "today": date string,
  "account_open_date": date string,
  "purchase_date": date string,
  "transaction_amount": number,
  "card_type": string,
  "dispute_reason": string,
  "contacted_merchant": boolean,
  "prior_dispute_dates": [date string, ...]
}
Dates may be MM/DD/YYYY, YYYY-MM-DD, or ISO timestamps beginning YYYY-MM-DD.
"""
import json
import sys
from datetime import datetime, date
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
QUALIFYING = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
FRAUD = "unauthorized_fraudulent_charge"


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # ISO timestamps are accepted by taking their calendar-date portion.
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise ValueError(f"{field} is not a supported date: {value!r}") from exc


def main(data):
    today = parse_date(data.get("today"), "today")
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    purchase = parse_date(data.get("purchase_date"), "purchase_date")
    try:
        amount = Decimal(str(data.get("transaction_amount")))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("transaction_amount must be numeric") from exc
    if amount.is_nan() or amount.is_infinite() or amount < 0:
        raise ValueError("transaction_amount must be a finite nonnegative number")
    reason = data.get("dispute_reason")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        raise ValueError("contacted_merchant must be boolean")
    tier = data.get("card_type")
    if tier not in LIMITS:
        raise ValueError("card_type has no known provisional-credit limit")
    raw_history = data.get("prior_dispute_dates")
    if not isinstance(raw_history, list):
        raise ValueError("prior_dispute_dates must be a list")
    history = [parse_date(x, "prior_dispute_dates entry") for x in raw_history]
    # "Past 12 months" is a calendar-year lookback, inclusive of today.
    # Handle a February 29 current date without third-party dependencies.
    try:
        window_start = today.replace(year=today.year - 1)
    except ValueError:
        window_start = today.replace(year=today.year - 1, month=2, day=28)
    prior_count = sum(window_start <= d <= today for d in history)

    failures = []
    if opened > today or (today - opened).days < 60:
        failures.append("account_not_open_at_least_60_days")
    if reason not in QUALIFYING:
        failures.append("reason_not_eligible")
    if reason == "goods_services_not_received" and (today - purchase).days <= 30:
        failures.append("goods_not_received_purchase_not_more_than_30_days_old")
    if amount < Decimal("25"):
        failures.append("amount_below_25")
    if amount > LIMITS[tier]:
        failures.append("amount_exceeds_card_tier_limit")
    if prior_count > 2:
        failures.append("more_than_two_prior_disputes_in_12_months")
    if reason != FRAUD and not contacted:
        failures.append("merchant_not_contacted_for_nonfraud_dispute")
    return {
        "eligible": not failures,
        "prior_disputes_in_last_12_months": prior_count,
        "reasons": failures,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
