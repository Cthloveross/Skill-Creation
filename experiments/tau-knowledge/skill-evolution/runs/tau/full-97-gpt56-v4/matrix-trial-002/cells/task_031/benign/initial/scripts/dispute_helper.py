#!/usr/bin/env python3
"""Validate dispute payloads and calculate policy-based provisional-credit eligibility.

Read one JSON object from stdin and write one JSON object to stdout.
Operations:
  eligibility: calculate eligibility from fully known runtime facts.
  validate_payload: validate the payload supplied to the filing tool.
"""
import datetime as dt
import json
import re
import sys
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
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_LIMITS = {
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
DATE_FORMAT = "%m/%d/%Y"


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an MM/DD/YYYY string")
    try:
        return dt.datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        raise ValueError(f"{field} must be a real date in MM/DD/YYYY format")


def decimal_amount(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount


def eligibility(data):
    opened = parse_date(data.get("account_open_date"), "account_open_date")
    as_of = parse_date(data.get("as_of_date"), "as_of_date")
    purchase = parse_date(data.get("purchase_date"), "purchase_date")
    amount = decimal_amount(data.get("transaction_amount"), "transaction_amount")
    reason = data.get("dispute_reason")
    card_type = data.get("card_type")
    contacted = data.get("contacted_merchant")
    prior = data.get("prior_disputes_12_months")
    if reason not in REASONS:
        raise ValueError("dispute_reason is not an allowed code")
    if card_type not in TIER_LIMITS:
        raise ValueError("card_type is not recognized by the provisional-credit tier policy")
    if not isinstance(contacted, bool):
        raise ValueError("contacted_merchant must be boolean")
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        raise ValueError("prior_disputes_12_months must be a non-negative integer")

    failures = []
    if (as_of - opened).days < 60:
        failures.append("account_open_less_than_60_days")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        failures.append("reason_not_eligible")
    if reason == "goods_services_not_received" and (as_of - purchase).days <= 30:
        failures.append("goods_not_received_purchase_not_more_than_30_days_old")
    if amount < Decimal("25"):
        failures.append("amount_under_25")
    if amount > TIER_LIMITS[card_type]:
        failures.append("amount_exceeds_card_tier_limit")
    if prior > 2:
        failures.append("more_than_two_prior_disputes_in_12_months")
    if reason != "unauthorized_fraudulent_charge" and not contacted:
        failures.append("merchant_not_contacted_for_nonfraud_dispute")
    return {"eligible": not failures, "reasons": failures}


def validate_payload(payload):
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be an object"]}
    errors = []
    strings = ["transaction_id", "card_last_4_digits", "full_name", "user_id", "phone", "email", "address"]
    for key in strings:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(payload.get("card_last_4_digits"), str) or not re.fullmatch(r"\d{4}", payload.get("card_last_4_digits", "")):
        errors.append("card_last_4_digits must contain exactly four digits")
    if payload.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    if not isinstance(payload.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    if not isinstance(payload.get("eligible_for_provisional_credit"), bool):
        errors.append("eligible_for_provisional_credit must be boolean")
    if payload.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not an allowed code")
    resolution = payload.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not an allowed code")
    for key in ("purchase_date", "issue_noticed_date"):
        try:
            parse_date(payload.get(key), key)
        except ValueError as exc:
            errors.append(str(exc))
    has_partial = "partial_refund_amount" in payload and payload.get("partial_refund_amount") is not None
    if resolution == "partial_refund":
        if not has_partial:
            errors.append("partial_refund_amount is required for partial_refund")
        else:
            try:
                if decimal_amount(payload["partial_refund_amount"], "partial_refund_amount") <= 0:
                    errors.append("partial_refund_amount must be greater than zero")
            except ValueError as exc:
                errors.append(str(exc))
    elif has_partial:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")
    return {"valid": not errors, "errors": errors}


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
        operation = data.get("operation")
        if operation == "eligibility":
            result = eligibility(data)
        elif operation == "validate_payload":
            result = validate_payload(data.get("payload"))
        else:
            raise ValueError("operation must be eligibility or validate_payload")
    except (ValueError, TypeError) as exc:
        result = {"error": str(exc)}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
