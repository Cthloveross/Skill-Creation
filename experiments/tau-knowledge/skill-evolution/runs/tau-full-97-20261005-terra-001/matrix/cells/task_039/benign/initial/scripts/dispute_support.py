#!/usr/bin/env python3
"""Deterministic validation and provisional-credit eligibility helper.

Input is one JSON object on stdin. Operations:
- eligibility: account_open_date, filing_date, purchase_date, reason, amount,
  card_type, previous_disputes_12_months, contacted_merchant.
- validate_payload: payload containing the filing-tool arguments.
Output is one JSON object on stdout. This script performs no external calls.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
CARD_ACTIONS = {"keep_active", "cancel_and_reissue"}
TIERS = {
    "Bronze Rewards Card": ("entry", Decimal("2500")),
    "EcoCard": ("entry", Decimal("2500")),
    "Business Bronze Rewards Card": ("entry", Decimal("2500")),
    "Crypto-Cash Back Card": ("entry", Decimal("2500")),
    "Silver Rewards Card": ("mid", Decimal("5000")),
    "Business Silver Rewards Card": ("mid", Decimal("5000")),
    "Green Rewards Card": ("mid", Decimal("5000")),
    "Silver Zoom Card": ("mid", Decimal("5000")),
    "Gold Rewards Card": ("premium", Decimal("10000")),
    "Business Gold Rewards Card": ("premium", Decimal("10000")),
    "Platinum Rewards Card": ("elite", Decimal("15000")),
    "Business Platinum Rewards Card": ("elite", Decimal("15000")),
    "Diamond Elite Card": ("invitation", Decimal("25000")),
}

def date_value(value):
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Supports timestamps returned by an internal history lookup.
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("date must use MM/DD/YYYY, YYYY-MM-DD, or ISO timestamp") from exc

def money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be numeric") from exc
    if not amount.is_finite():
        raise ValueError("amount must be finite")
    return amount

def eligibility(data):
    failures = []
    try:
        opened = date_value(data.get("account_open_date"))
        filed = date_value(data.get("filing_date"))
        purchase = date_value(data.get("purchase_date"))
        if opened > filed:
            failures.append("account_open_date is after filing_date")
        elif (filed - opened).days < 60:
            failures.append("account is less than 60 days old")
    except ValueError as exc:
        failures.append("invalid account or filing date: " + str(exc))
        filed = purchase = None
    reason = data.get("reason")
    if reason not in REASONS:
        failures.append("unsupported dispute reason")
    elif reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        failures.append("reason is not eligible for provisional credit")
    if reason == "goods_services_not_received" and filed and purchase:
        if (filed - purchase).days <= 30:
            failures.append("goods/services-not-received purchase is not more than 30 days old")
    try:
        amount = money(data.get("amount"))
        if amount < Decimal("25"):
            failures.append("transaction amount is below 25.00")
    except ValueError as exc:
        amount = None
        failures.append(str(exc))
    tier_info = TIERS.get(data.get("card_type"))
    tier = None
    limit = None
    if tier_info is None:
        failures.append("unknown card tier")
    else:
        tier, limit = tier_info
        if amount is not None and amount > limit:
            failures.append("transaction amount exceeds the tier provisional-credit limit")
    count = data.get("previous_disputes_12_months")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        failures.append("previous_disputes_12_months must be a nonnegative integer")
    elif count > 2:
        failures.append("more than two disputes were filed in the past 12 months")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        failures.append("contacted_merchant must be boolean")
    elif reason != "unauthorized_fraudulent_charge" and not contacted:
        failures.append("merchant was not contacted for a non-fraud dispute")
    return {
        "eligible_for_provisional_credit": not failures,
        "card_tier": tier,
        "maximum_provisional_credit": float(limit) if limit is not None else None,
        "failed_conditions": failures,
    }

def validate_payload(payload):
    errors = []
    required = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
        "phone", "email", "address", "contacted_merchant", "purchase_date",
        "issue_noticed_date", "dispute_reason", "resolution_requested",
        "eligible_for_provisional_credit",
    ]
    for key in required:
        if key not in payload or payload[key] is None or payload[key] == "":
            errors.append("missing required field: " + key)
    if payload.get("card_action") not in CARD_ACTIONS:
        errors.append("card_action is invalid")
    digits = payload.get("card_last_4_digits")
    if not isinstance(digits, str) or len(digits) != 4 or not digits.isdigit():
        errors.append("card_last_4_digits must be exactly four digits")
    if not isinstance(payload.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    if not isinstance(payload.get("eligible_for_provisional_credit"), bool):
        errors.append("eligible_for_provisional_credit must be boolean")
    if payload.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is invalid")
    resolution = payload.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is invalid")
    partial_present = "partial_refund_amount" in payload and payload.get("partial_refund_amount") is not None
    if resolution == "partial_refund":
        if not partial_present:
            errors.append("partial_refund_amount is required for partial_refund")
        else:
            try:
                if money(payload["partial_refund_amount"]) <= 0:
                    errors.append("partial_refund_amount must be positive")
            except ValueError as exc:
                errors.append(str(exc))
    elif partial_present:
        errors.append("partial_refund_amount is allowed only for partial_refund")
    for key in ("purchase_date", "issue_noticed_date"):
        if key in payload and payload[key] not in (None, ""):
            try:
                # Filing API specifically requires this display format.
                datetime.strptime(payload[key], "%m/%d/%Y")
            except (TypeError, ValueError):
                errors.append(key + " must use MM/DD/YYYY")
    return {"valid": not errors, "errors": errors}

def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        operation = data.get("operation")
        if operation == "eligibility":
            result = eligibility(data)
        elif operation == "validate_payload":
            payload = data.get("payload")
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            result = validate_payload(payload)
        else:
            raise ValueError("operation must be eligibility or validate_payload")
        print(json.dumps(result, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)

if __name__ == "__main__":
    main()
