#!/usr/bin/env python3
"""Evaluate provisional-credit eligibility for credit-card disputes.

Reads one JSON object from stdin and writes one JSON object to stdout. This
helper performs no network, account, or banking actions.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

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

ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}

ALL_REASONS = ELIGIBLE_REASONS | {
    "incorrect_amount",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}


def parse_date(value):
    """Return a date from supported date/timestamp formats, otherwise None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_amount(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount >= 0 else None


def twelve_months_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # February 29 in a leap year
        return day.replace(year=day.year - 1, month=2, day=28)


def history_count(history, as_of, problems):
    """Count dated records in the inclusive preceding twelve-month window."""
    if not isinstance(history, list):
        problems.append("dispute_history must be a list of records")
        return None

    lower_bound = twelve_months_before(as_of)
    count = 0
    for index, record in enumerate(history):
        raw_date = record.get("dispute_date") if isinstance(record, dict) else record
        dispute_date = parse_date(raw_date)
        if dispute_date is None:
            problems.append("dispute_history[%d] has no parseable dispute_date" % index)
        elif lower_bound <= dispute_date <= as_of:
            count += 1
    return count


def insufficient(transaction_id, missing, facts=None):
    return {
        "transaction_id": transaction_id,
        "status": "insufficient_data",
        "eligible_for_provisional_credit": None,
        "failed_conditions": [],
        "missing_or_invalid": missing,
        "facts": facts or {},
    }


def evaluate(dispute, as_of, prior_disputes):
    if not isinstance(dispute, dict):
        return insufficient(None, ["dispute must be an object"])

    transaction_id = dispute.get("transaction_id")
    account_open = parse_date(dispute.get("account_open_date"))
    purchase_date = parse_date(dispute.get("purchase_date"))
    amount = parse_amount(dispute.get("transaction_amount"))
    card_type = dispute.get("card_type")
    reason = dispute.get("dispute_reason")
    contacted = dispute.get("contacted_merchant")
    missing = []

    if not isinstance(transaction_id, str) or not transaction_id.strip():
        missing.append("transaction_id must be a non-empty string")
    if account_open is None:
        missing.append("account_open_date must be a parseable date")
    if purchase_date is None:
        missing.append("purchase_date must be a parseable date")
    if amount is None:
        missing.append("transaction_amount must be a non-negative number")
    if card_type not in TIER_LIMITS:
        missing.append("card_type does not map to a supported provisional-credit tier")
    if reason not in ALL_REASONS:
        missing.append("dispute_reason is not a supported reason code")
    if not isinstance(contacted, bool):
        missing.append("contacted_merchant must be boolean")
    if prior_disputes is None:
        missing.append("prior dispute count could not be determined")
    if missing:
        return insufficient(transaction_id, missing)

    account_age = (as_of - account_open).days
    purchase_age = (as_of - purchase_date).days
    limit = TIER_LIMITS[card_type]
    failed = []

    if account_age < 60:
        failed.append("account has been open fewer than 60 days")
    if reason not in ELIGIBLE_REASONS:
        failed.append("dispute reason is not eligible for provisional credit")
    if reason == "goods_services_not_received" and purchase_age <= 30:
        failed.append("goods/services-not-received purchase is not more than 30 days old")
    if amount < Decimal("25.00"):
        failed.append("transaction amount is under $25.00")
    if amount > limit:
        failed.append("transaction amount exceeds the card tier limit")
    if prior_disputes > 2:
        failed.append("customer has filed more than two disputes in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and not contacted:
        failed.append("customer did not contact the merchant for a non-fraud dispute")

    return {
        "transaction_id": transaction_id,
        "status": "ready",
        "eligible_for_provisional_credit": not failed,
        "failed_conditions": failed,
        "missing_or_invalid": [],
        "facts": {
            "account_age_days": account_age,
            "purchase_age_days": purchase_age,
            "transaction_amount": format(amount, "f"),
            "card_type": card_type,
            "tier_limit": format(limit, "f"),
            "prior_disputes_in_past_12_months": prior_disputes,
        },
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "insufficient_data", "error": "invalid JSON: %s" % exc.msg}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"status": "insufficient_data", "error": "top-level JSON must be an object"}))
        return

    as_of = parse_date(payload.get("as_of_date"))
    disputes = payload.get("disputes")
    if as_of is None or not isinstance(disputes, list):
        print(json.dumps({
            "status": "insufficient_data",
            "error": "as_of_date must be a parseable date and disputes must be a list",
            "results": [],
        }))
        return

    history_problems = []
    prior_disputes = history_count(payload.get("dispute_history"), as_of, history_problems)
    results = [evaluate(dispute, as_of, prior_disputes) for dispute in disputes]
    if history_problems:
        for result in results:
            result["status"] = "insufficient_data"
            result["eligible_for_provisional_credit"] = None
            result["missing_or_invalid"].extend(history_problems)

    print(json.dumps({
        "as_of_date": as_of.strftime("%m/%d/%Y"),
        "results": results,
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
