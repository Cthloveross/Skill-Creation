#!/usr/bin/env python3
"""Assess documented provisional-credit eligibility from explicit case facts.
Reads JSON from stdin and writes JSON to stdout.  It performs no network or bank action.
"""
import json
import sys
from datetime import datetime, date
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
FRAUD = "unauthorized_fraudulent_charge"


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("must use MM/DD/YYYY or YYYY-MM-DD")


def money(value):
    if isinstance(value, bool):
        raise ValueError("must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("must be a number")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


def assess(case, as_of):
    result = {
        "case_id": case.get("case_id"),
        "eligible": None,
        "tier_limit": None,
        "failures": [],
        "missing_or_invalid": [],
    }
    required = ["card_type", "account_open_date", "transaction_amount", "purchase_date",
                "dispute_reason", "contacted_merchant", "prior_disputes_12_months"]
    for key in required:
        if key not in case or case[key] is None:
            result["missing_or_invalid"].append(key + " is required")
    if result["missing_or_invalid"]:
        return result

    try:
        opened = parse_date(case["account_open_date"])
    except ValueError as exc:
        result["missing_or_invalid"].append("account_open_date " + str(exc))
        opened = None
    try:
        purchased = parse_date(case["purchase_date"])
    except ValueError as exc:
        result["missing_or_invalid"].append("purchase_date " + str(exc))
        purchased = None
    try:
        amount = money(case["transaction_amount"])
    except ValueError as exc:
        result["missing_or_invalid"].append("transaction_amount " + str(exc))
        amount = None
    contacted = case["contacted_merchant"]
    if not isinstance(contacted, bool):
        result["missing_or_invalid"].append("contacted_merchant must be boolean")
    prior = case["prior_disputes_12_months"]
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        result["missing_or_invalid"].append("prior_disputes_12_months must be a nonnegative integer")
    card_type = case["card_type"]
    if not isinstance(card_type, str) or card_type not in TIER_LIMITS:
        result["missing_or_invalid"].append("card_type is not a recognized tier")
    else:
        result["tier_limit"] = float(TIER_LIMITS[card_type])
    reason = case["dispute_reason"]
    if not isinstance(reason, str):
        result["missing_or_invalid"].append("dispute_reason must be a string")
    if result["missing_or_invalid"]:
        return result

    if opened > as_of or (as_of - opened).days < 60:
        result["failures"].append("account has not been open at least 60 days")
    if reason not in ELIGIBLE_REASONS:
        result["failures"].append("dispute reason is not eligible for provisional credit")
    if amount < Decimal("25.00"):
        result["failures"].append("transaction amount is below $25.00")
    elif amount > TIER_LIMITS[card_type]:
        result["failures"].append("transaction amount exceeds the card tier limit")
    if prior > 2:
        result["failures"].append("more than two prior disputes in the past 12 months")
    if reason != FRAUD and not contacted:
        result["failures"].append("merchant was not contacted for a non-fraud dispute")
    if reason == "goods_services_not_received":
        if purchased > as_of or (as_of - purchased).days <= 30:
            result["failures"].append("goods/services-not-received purchase is not more than 30 days old")
    result["eligible"] = not result["failures"]
    return result


def main():
    try:
        data = json.load(sys.stdin)
        as_of = parse_date(data["as_of_date"])
        cases = data["cases"]
        if not isinstance(cases, list):
            raise ValueError("cases must be a list")
        output = {"as_of_date": as_of.strftime("%m/%d/%Y"),
                  "results": [assess(c, as_of) if isinstance(c, dict) else {
                      "case_id": None, "eligible": None, "tier_limit": None,
                      "failures": [], "missing_or_invalid": ["case must be an object"]
                  } for c in cases]}
    except (KeyError, ValueError, TypeError) as exc:
        output = {"error": str(exc), "results": []}
    print(json.dumps(output, separators=(",", ":")))


if __name__ == "__main__":
    main()
