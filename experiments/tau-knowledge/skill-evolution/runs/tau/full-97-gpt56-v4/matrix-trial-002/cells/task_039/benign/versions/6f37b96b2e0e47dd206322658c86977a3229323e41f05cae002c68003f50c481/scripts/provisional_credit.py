#!/usr/bin/env python3
"""Assess documented provisional-credit eligibility from JSON stdin."""
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

LIMITS = {
    "entry": Decimal("2500.00"),
    "mid": Decimal("5000.00"),
    "premium": Decimal("10000.00"),
    "elite": Decimal("15000.00"),
    "invitation": Decimal("25000.00"),
}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}

def date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be MM/DD/YYYY")
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise ValueError(f"{field} must be MM/DD/YYYY")

def money(value):
    if isinstance(value, bool):
        raise ValueError("amount must be numeric")
    text = str(value).strip().replace(",", "")
    text = re.sub(r"^\$", "", text)
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise ValueError("amount must be numeric")
    if result < 0:
        raise ValueError("amount cannot be negative")
    return result

def main(data):
    opened = date(data.get("account_open_date"), "account_open_date")
    evaluated = date(data.get("evaluation_date"), "evaluation_date")
    purchased = date(data.get("purchase_date"), "purchase_date")
    if purchased > evaluated:
        raise ValueError("purchase_date cannot be after evaluation_date")
    if opened > evaluated:
        raise ValueError("account_open_date cannot be after evaluation_date")
    amount = money(data.get("amount"))
    tier = data.get("card_tier")
    if not isinstance(tier, str) or tier.lower() not in LIMITS:
        raise ValueError("card_tier must be entry, mid, premium, elite, or invitation")
    tier = tier.lower()
    reason = data.get("reason")
    prior = data.get("prior_disputes_12_months")
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        raise ValueError("prior_disputes_12_months must be a nonnegative integer")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        raise ValueError("contacted_merchant must be boolean")

    failures = []
    if (evaluated - opened).days < 60:
        failures.append("account_open_less_than_60_days")
    if reason not in ELIGIBLE_REASONS:
        failures.append("reason_not_eligible")
    if reason == "goods_services_not_received" and (evaluated - purchased).days <= 30:
        failures.append("goods_not_received_purchase_not_more_than_30_days_old")
    if amount < Decimal("25.00"):
        failures.append("amount_under_25")
    if amount > LIMITS[tier]:
        failures.append("amount_exceeds_tier_limit")
    if prior > 2:
        failures.append("more_than_two_prior_disputes_in_12_months")
    if reason != "unauthorized_fraudulent_charge" and not contacted:
        failures.append("merchant_not_contacted_for_non_fraud_dispute")
    return {
        "eligible_for_provisional_credit": not failures,
        "reasons": failures,
        "normalized_amount": f"{amount:.2f}",
        "maximum_limit": f"{LIMITS[tier]:.2f}",
    }

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload)))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
