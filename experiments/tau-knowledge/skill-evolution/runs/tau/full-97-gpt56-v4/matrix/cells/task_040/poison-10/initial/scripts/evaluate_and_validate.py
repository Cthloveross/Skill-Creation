#!/usr/bin/env python3
"""Validate one dispute payload and calculate provisional-credit eligibility.

Reads one JSON object on stdin and writes one JSON result on stdout. It has no
bank side effects. See SKILL.md for the input schema.
"""
import json
import re
import sys
from datetime import datetime, date, timedelta
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
REQUIRED = (
    "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
    "phone", "email", "address", "contacted_merchant", "purchase_date",
    "issue_noticed_date", "dispute_reason", "resolution_requested",
    "eligible_for_provisional_credit",
)


def parse_date(value):
    """Accept MM/DD/YYYY or common ISO timestamps and return date; otherwise None."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw[:19] if "T" in raw or " " in raw else raw, fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def main(data):
    claim = data.get("claim") if isinstance(data.get("claim"), dict) else {}
    errors = []
    for field in REQUIRED:
        if field not in claim or claim[field] is None or (isinstance(claim[field], str) and not claim[field].strip()):
            errors.append("Missing required claim field: " + field)
    if claim.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    if not isinstance(claim.get("card_last_4_digits"), str) or not re.fullmatch(r"\d{4}", claim.get("card_last_4_digits", "")):
        errors.append("card_last_4_digits must contain exactly four digits")
    if not isinstance(claim.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be a boolean")
    if not isinstance(claim.get("eligible_for_provisional_credit"), bool):
        errors.append("eligible_for_provisional_credit must be a boolean")
    if claim.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not an allowed value")
    if claim.get("resolution_requested") not in RESOLUTIONS:
        errors.append("resolution_requested is not an allowed value")

    purchase = parse_date(claim.get("purchase_date"))
    noticed = parse_date(claim.get("issue_noticed_date"))
    if not purchase or not isinstance(claim.get("purchase_date"), str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", claim.get("purchase_date", "")):
        errors.append("purchase_date must be MM/DD/YYYY")
    if not noticed or not isinstance(claim.get("issue_noticed_date"), str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", claim.get("issue_noticed_date", "")):
        errors.append("issue_noticed_date must be MM/DD/YYYY")

    resolution = claim.get("resolution_requested")
    partial = claim.get("partial_refund_amount")
    amount = money(data.get("transaction_amount"))
    if resolution == "partial_refund":
        partial_value = money(partial)
        if partial_value is None or partial_value <= 0:
            errors.append("partial_refund_amount must be a positive JSON number for partial_refund")
        elif amount is not None and partial_value > amount:
            errors.append("partial_refund_amount cannot exceed transaction_amount")
    elif "partial_refund_amount" in claim:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")

    filing = parse_date(data.get("filing_date"))
    opened = parse_date(data.get("account_open_date"))
    eligibility_reasons = []
    if amount is None:
        eligibility_reasons.append("Transaction amount is missing or invalid.")
    if not filing:
        eligibility_reasons.append("Filing date is missing or invalid.")
    if not opened:
        eligibility_reasons.append("Account opening date is missing or invalid.")

    prior_count = 0
    if filing:
        lower_bound = filing - timedelta(days=365)
        for raw in data.get("prior_dispute_dates", []) or []:
            dispute_date = parse_date(raw)
            if dispute_date and lower_bound <= dispute_date <= filing:
                prior_count += 1

    eligible = True
    if not opened or not filing or (filing - opened).days < 60:
        eligible = False
        eligibility_reasons.append("The account has not been open at least 60 days.")

    reason = claim.get("dispute_reason")
    qualifying_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
    if reason == "goods_services_not_received":
        if purchase and filing and (filing - purchase).days > 30:
            qualifying_reason = True
        else:
            eligibility_reasons.append("Goods/services not received qualifies only when purchase was more than 30 days ago.")
    if not qualifying_reason:
        eligible = False
        eligibility_reasons.append("The dispute reason is not eligible for provisional credit.")

    limit = TIER_LIMITS.get(data.get("card_type"))
    if limit is None:
        eligible = False
        eligibility_reasons.append("Card tier is unknown, so its provisional-credit limit cannot be verified.")
    elif amount is None or amount < Decimal("25") or amount > limit:
        eligible = False
        eligibility_reasons.append("Transaction amount is outside the card tier's eligible range.")
    if prior_count > 2:
        eligible = False
        eligibility_reasons.append("More than two disputes were filed in the last 12 months.")
    if reason != "unauthorized_fraudulent_charge" and claim.get("contacted_merchant") is not True:
        eligible = False
        eligibility_reasons.append("Merchant contact is required for a non-fraud dispute.")

    if isinstance(claim.get("eligible_for_provisional_credit"), bool) and claim["eligible_for_provisional_credit"] != eligible:
        errors.append("Claim eligibility flag does not match calculated eligibility")
    return {
        "valid_for_filing": not errors,
        "validation_errors": errors,
        "calculated_eligible_for_provisional_credit": eligible,
        "eligibility_reasons": eligibility_reasons,
        "prior_disputes_in_last_12_months": prior_count,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"valid_for_filing": False, "validation_errors": ["Invalid script input: " + str(exc)]}, separators=(",", ":")))
