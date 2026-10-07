#!/usr/bin/env python3
"""Compute conservative provisional-credit eligibility.

Read one JSON object from stdin and write one JSON result to stdout. See SKILL.md
for the input schema. The result contains eligible_for_provisional_credit (bool),
blockers (known disqualifiers), missing_fields (facts that prevent approval), and
computed values useful for audit.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

DATE_FORMAT = "%m/%d/%Y"
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
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "goods_services_not_received",
}
VALID_REASONS = ELIGIBLE_REASONS | {
    "incorrect_amount", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}

def parse_date(value, field, missing, blockers):
    if value is None or value == "":
        missing.append(field)
        return None
    if not isinstance(value, str):
        blockers.append(field + " must be MM/DD/YYYY")
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        blockers.append(field + " must be MM/DD/YYYY")
        return None

def main(data):
    missing, blockers = [], []
    opened = parse_date(data.get("account_open_date"), "account_open_date", missing, blockers)
    reference = parse_date(data.get("reference_date"), "reference_date", missing, blockers)
    purchase = parse_date(data.get("purchase_date"), "purchase_date", missing, blockers)

    amount = None
    raw_amount = data.get("transaction_amount")
    if raw_amount is None or raw_amount == "":
        missing.append("transaction_amount")
    else:
        try:
            amount = Decimal(str(raw_amount))
            if not amount.is_finite():
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            blockers.append("transaction_amount must be numeric")

    card_type = data.get("card_type")
    if not card_type:
        missing.append("card_type")
    elif card_type not in LIMITS:
        blockers.append("unsupported card_type")

    reason = data.get("dispute_reason")
    if not reason:
        missing.append("dispute_reason")
    elif reason not in VALID_REASONS:
        blockers.append("invalid dispute_reason")
    elif reason not in ELIGIBLE_REASONS:
        blockers.append("dispute_reason is not eligible for provisional credit")

    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        missing.append("contacted_merchant")

    previous = data.get("previous_disputes_12_months")
    if previous is None or previous == "":
        missing.append("previous_disputes_12_months")
    elif isinstance(previous, bool) or not isinstance(previous, int) or previous < 0:
        blockers.append("previous_disputes_12_months must be a nonnegative integer")
    elif previous > 2:
        blockers.append("more than 2 prior disputes in 12 months")

    if opened and reference:
        age_days = (reference - opened).days
        if age_days < 60:
            blockers.append("account has been open fewer than 60 days")
    else:
        age_days = None

    if purchase and reference:
        purchase_age_days = (reference - purchase).days
        if purchase_age_days < 0:
            blockers.append("purchase_date is after reference_date")
        if reason == "goods_services_not_received" and purchase_age_days <= 30:
            blockers.append("goods/services-not-received purchase is not more than 30 days old")
    else:
        purchase_age_days = None

    if amount is not None:
        if amount < Decimal("25"):
            blockers.append("transaction amount is under $25.00")
        if card_type in LIMITS and amount > LIMITS[card_type]:
            blockers.append("transaction amount exceeds card tier limit")

    if reason and reason != "unauthorized_fraudulent_charge" and contacted is False:
        blockers.append("merchant was not contacted for a non-fraud dispute")

    result = {
        "eligible_for_provisional_credit": not blockers and not missing,
        "blockers": blockers,
        "missing_fields": missing,
        "account_age_days": age_days,
        "purchase_age_days": purchase_age_days,
        "tier_limit": str(LIMITS[card_type]) if card_type in LIMITS else None,
    }
    return result

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
