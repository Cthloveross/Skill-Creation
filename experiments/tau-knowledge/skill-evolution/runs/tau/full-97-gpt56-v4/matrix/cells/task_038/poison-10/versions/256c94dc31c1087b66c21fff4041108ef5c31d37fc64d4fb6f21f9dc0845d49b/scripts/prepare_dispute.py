#!/usr/bin/env python3
"""Validate one dispute payload and calculate provisional-credit eligibility.

Reads one JSON object from stdin and writes one JSON object to stdout. This script has
no banking side effects. See SKILL.md for the input and output schema.
"""
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
ENTRY = {"Bronze Rewards Card", "EcoCard", "Business Bronze Rewards Card", "Crypto-Cash Back Card"}
MID = {"Silver Rewards Card", "Business Silver Rewards Card", "Green Rewards Card", "Silver Zoom Card"}
PREMIUM = {"Gold Rewards Card", "Business Gold Rewards Card"}
ELITE = {"Platinum Rewards Card", "Business Platinum Rewards Card"}
INVITATION = {"Diamond Elite Card"}


def date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be MM/DD/YYYY")
        return None
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{field} must be MM/DD/YYYY")
        return None


def money(value, field, errors):
    try:
        cleaned = str(value).replace("$", "").replace(",", "").strip()
        result = Decimal(cleaned)
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number")
        return None


def cap_for(card_type):
    if card_type in ENTRY:
        return Decimal("2500")
    if card_type in MID:
        return Decimal("5000")
    if card_type in PREMIUM:
        return Decimal("10000")
    if card_type in ELITE:
        return Decimal("15000")
    if card_type in INVITATION:
        return Decimal("25000")
    return None


def main(data):
    errors = []
    dispute = data.get("dispute")
    if not isinstance(dispute, dict):
        return {"ok": False, "errors": ["dispute must be an object"], "payload": None, "eligibility_checks": {}}

    required_strings = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
        "phone", "email", "address", "purchase_date", "issue_noticed_date",
        "dispute_reason", "resolution_requested",
    ]
    for key in required_strings:
        if not isinstance(dispute.get(key), str) or not dispute[key].strip():
            errors.append(f"{key} is required and must be a nonempty string")
    if dispute.get("card_action") not in ACTIONS:
        errors.append("card_action is invalid")
    if isinstance(dispute.get("card_last_4_digits"), str) and not re.fullmatch(r"\d{4}", dispute["card_last_4_digits"]):
        errors.append("card_last_4_digits must contain exactly four digits")
    if not isinstance(dispute.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    reason = dispute.get("dispute_reason")
    resolution = dispute.get("resolution_requested")
    if reason not in REASONS:
        errors.append("dispute_reason is invalid")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is invalid")
    if resolution == "partial_refund":
        partial = money(dispute.get("partial_refund_amount"), "partial_refund_amount", errors)
        if partial is not None and partial <= 0:
            errors.append("partial_refund_amount must be positive")
    elif "partial_refund_amount" in dispute:
        errors.append("partial_refund_amount is permitted only for partial_refund")

    purchase = date(dispute.get("purchase_date"), "purchase_date", errors)
    noticed = date(dispute.get("issue_noticed_date"), "issue_noticed_date", errors)
    opened = date(data.get("account_open_date"), "account_open_date", errors)
    filing = date(data.get("filing_date"), "filing_date", errors)
    amount = money(data.get("transaction_amount"), "transaction_amount", errors)
    if amount is not None and amount <= 0:
        errors.append("transaction_amount must be positive")
    if purchase and noticed and noticed < purchase:
        errors.append("issue_noticed_date cannot precede purchase_date")
    if purchase and filing and purchase > filing:
        errors.append("purchase_date cannot be after filing_date")
    if not isinstance(data.get("prior_disputes_last_12_months"), int) or data.get("prior_disputes_last_12_months", -1) < 0:
        errors.append("prior_disputes_last_12_months must be a nonnegative integer")

    cap = cap_for(data.get("card_type"))
    if cap is None:
        errors.append("card_type is unsupported for provisional-credit tier calculation")
    checks = {}
    if not errors:
        checks["account_open_at_least_60_days"] = (filing - opened).days >= 60
        qualifying_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
        if reason == "goods_services_not_received":
            qualifying_reason = (filing - purchase).days > 30
        checks["qualifying_reason_and_delivery_age"] = qualifying_reason
        checks["amount_within_minimum_and_tier_cap"] = Decimal("25") <= amount <= cap
        checks["no_more_than_two_prior_disputes"] = data["prior_disputes_last_12_months"] <= 2
        checks["merchant_contact_requirement"] = (reason == "unauthorized_fraudulent_charge" or dispute["contacted_merchant"])
        eligible = all(checks.values())
        payload = dict(dispute)
        payload["eligible_for_provisional_credit"] = eligible
        return {"ok": True, "errors": [], "payload": payload, "eligibility_checks": checks}
    return {"ok": False, "errors": errors, "payload": None, "eligibility_checks": checks}


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "payload": None, "eligibility_checks": {}}))
        sys.exit(1)
