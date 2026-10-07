#!/usr/bin/env python3
"""Validate a prospective dispute and evaluate documented provisional-credit rules.

Reads a single JSON object from stdin and writes a JSON result to stdout.
It is deliberately side-effect free and does not make banking-tool calls.
"""

import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge",
    "duplicate_charge",
    "incorrect_amount",
    "goods_services_not_received",
    "goods_services_not_as_described",
    "canceled_subscription_still_charging",
    "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
TIER_LIMITS = {
    "Bronze Rewards Card": Decimal("2500.00"),
    "EcoCard": Decimal("2500.00"),
    "Business Bronze Rewards Card": Decimal("2500.00"),
    "Crypto-Cash Back Card": Decimal("2500.00"),
    # Some account records omit the word "Card" for this documented entry-tier product.
    "Crypto-Cash Back": Decimal("2500.00"),
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


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a date string")
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    errors.append(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")
    return None


def parse_money(value, field, errors):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not amount.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return amount


def main(data):
    errors = []
    open_date = parse_date(data.get("account_open_date"), "account_open_date", errors)
    purchase_date = parse_date(data.get("purchase_date"), "purchase_date", errors)
    current_date = parse_date(data.get("current_date"), "current_date", errors)
    amount = parse_money(data.get("transaction_amount"), "transaction_amount", errors)

    reason = data.get("dispute_reason")
    if reason not in REASONS:
        errors.append("dispute_reason is not a permitted value")
    resolution = data.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not a permitted value")

    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")

    prior_count = data.get("prior_disputes_last_12_months")
    if isinstance(prior_count, bool) or not isinstance(prior_count, int) or prior_count < 0:
        errors.append("prior_disputes_last_12_months must be a nonnegative integer")

    has_partial = "partial_refund_amount" in data and data.get("partial_refund_amount") is not None
    partial_amount = None
    if resolution == "partial_refund":
        if not has_partial:
            errors.append("partial_refund_amount is required for partial_refund")
        else:
            partial_amount = parse_money(data.get("partial_refund_amount"), "partial_refund_amount", errors)
            if partial_amount is not None and partial_amount <= 0:
                errors.append("partial_refund_amount must be positive")
            if amount is not None and partial_amount is not None and partial_amount > amount:
                errors.append("partial_refund_amount cannot exceed transaction_amount")
    elif has_partial:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")

    card_type = data.get("card_type")
    limit = TIER_LIMITS.get(card_type)
    if not isinstance(card_type, str) or limit is None:
        errors.append("card_type is not in the documented provisional-credit tier list")

    ineligible = []
    # Missing or malformed inputs yield false rather than an unsupported positive result.
    if open_date is None or current_date is None:
        ineligible.append("account age cannot be determined")
    elif (current_date - open_date).days < 60:
        ineligible.append("account has been open fewer than 60 days")

    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        ineligible.append("dispute reason is not eligible for provisional credit")
    elif reason == "goods_services_not_received":
        if purchase_date is None or current_date is None:
            ineligible.append("nonreceipt purchase age cannot be determined")
        elif (current_date - purchase_date).days <= 30:
            ineligible.append("nonreceipt purchase was not more than 30 days ago")

    if amount is None:
        ineligible.append("transaction amount cannot be determined")
    elif amount < Decimal("25.00"):
        ineligible.append("transaction amount is below $25.00")
    elif limit is None:
        ineligible.append("card provisional-credit limit cannot be determined")
    elif amount > limit:
        ineligible.append("transaction amount exceeds the card-tier limit")

    if isinstance(prior_count, int) and not isinstance(prior_count, bool):
        if prior_count > 2:
            ineligible.append("more than two disputes were filed in the past 12 months")
    else:
        ineligible.append("prior dispute count cannot be determined")

    if reason != "unauthorized_fraudulent_charge" and contacted is not True:
        ineligible.append("merchant was not contacted for a non-fraud dispute")

    valid = not errors
    eligible = valid and not ineligible
    return {
        "valid_input": valid,
        "validation_errors": errors,
        "eligible_for_provisional_credit": eligible,
        "ineligible_reasons": ineligible,
        "card_tier_limit": str(limit) if limit is not None else None,
        "partial_refund_amount": str(partial_amount) if partial_amount is not None else None,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({
            "valid_input": False,
            "validation_errors": [str(exc)],
            "eligible_for_provisional_credit": False,
            "ineligible_reasons": ["input could not be evaluated"],
            "card_tier_limit": None,
            "partial_refund_amount": None,
        }, sort_keys=True))
