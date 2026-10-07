#!/usr/bin/env python3
"""Evaluate the documented provisional-credit rules from JSON stdin."""
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
    "entry": Decimal("2500.00"),
    "mid": Decimal("5000.00"),
    "premium": Decimal("10000.00"),
    "elite": Decimal("15000.00"),
    "invitation": Decimal("25000.00"),
}
CARD_TYPE_TIERS = {
    "bronze rewards card": "entry",
    "bronze rewards": "entry",
    "ecocard": "entry",
    "business bronze rewards card": "entry",
    "business bronze": "entry",
    "crypto-cash back card": "entry",
    "silver rewards card": "mid",
    "silver rewards": "mid",
    "business silver rewards card": "mid",
    "business silver": "mid",
    "green rewards card": "mid",
    "green rewards": "mid",
    "silver zoom card": "mid",
    "silver zoom": "mid",
    "gold rewards card": "premium",
    "gold rewards": "premium",
    "business gold rewards card": "premium",
    "business gold": "premium",
    "platinum rewards card": "elite",
    "platinum rewards": "elite",
    "business platinum rewards card": "elite",
    "business platinum": "elite",
    "diamond elite card": "invitation",
    "diamond elite": "invitation",
}


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be MM/DD/YYYY")
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{field} must be MM/DD/YYYY")


def parse_amount(value):
    if isinstance(value, bool):
        raise ValueError("amount must be numeric")
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        amount = Decimal(cleaned)
    except (InvalidOperation, ValueError):
        raise ValueError("amount must be numeric")
    if amount < 0:
        raise ValueError("amount cannot be negative")
    return amount


def normalize_tier(value):
    if not isinstance(value, str):
        return None
    key = " ".join(value.lower().split())
    return key if key in TIER_LIMITS else CARD_TYPE_TIERS.get(key)


def main():
    try:
        data = json.load(sys.stdin)
        required = [
            "account_open_date", "as_of_date", "purchase_date", "reason", "amount",
            "card_tier", "disputes_past_12_months", "contacted_merchant",
        ]
        missing = [key for key in required if key not in data]
        if missing:
            raise ValueError("missing required fields: " + ", ".join(missing))
        opened = parse_date(data["account_open_date"], "account_open_date")
        as_of = parse_date(data["as_of_date"], "as_of_date")
        purchase = parse_date(data["purchase_date"], "purchase_date")
        amount = parse_amount(data["amount"])
        tier = normalize_tier(data["card_tier"])
        if not isinstance(data["disputes_past_12_months"], int) or isinstance(data["disputes_past_12_months"], bool):
            raise ValueError("disputes_past_12_months must be an integer")
        if data["disputes_past_12_months"] < 0:
            raise ValueError("disputes_past_12_months cannot be negative")
        if not isinstance(data["contacted_merchant"], bool):
            raise ValueError("contacted_merchant must be boolean")

        failures = []
        if as_of < opened or (as_of - opened).days < 60:
            failures.append("account has not been open for at least 60 days")
        reason = data["reason"]
        if reason not in ELIGIBLE_REASONS:
            failures.append("dispute reason is not eligible for provisional credit")
        if reason == "goods_services_not_received" and (as_of - purchase).days <= 30:
            failures.append("goods/services-not-received purchase is not more than 30 days old")
        if tier is None:
            failures.append("unrecognized card tier")
        else:
            limit = TIER_LIMITS[tier]
            if amount < Decimal("25.00"):
                failures.append("transaction amount is below $25.00")
            if amount > limit:
                failures.append(f"transaction amount exceeds the {tier} tier limit")
        if data["disputes_past_12_months"] > 2:
            failures.append("customer has more than two disputes in the past 12 months")
        if reason != "unauthorized_fraudulent_charge" and not data["contacted_merchant"]:
            failures.append("merchant was not contacted for a non-fraud dispute")

        print(json.dumps({
            "eligible": not failures,
            "failures": failures,
            "normalized_card_tier": tier,
            "amount": f"{amount:.2f}",
        }))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible": False, "failures": [str(exc)]}))


if __name__ == "__main__":
    main()
