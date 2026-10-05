#!/usr/bin/env python3
"""Validate and prepare a credit-card dispute filing.

Read one JSON object from stdin using the schema in SKILL.md. Write:
{
  "ready": bool,
  "errors": [str],
  "eligibility_determinate": bool,
  "eligible_for_provisional_credit": bool | null,
  "eligibility_checks": object,
  "payload": object | null
}
This program performs no banking action.
"""
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

ACTIONS = {"keep_active", "cancel_and_reissue"}
REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
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


def parse_date(value):
    """Accept a MM/DD/YYYY date or a timestamp beginning with one."""
    if not isinstance(value, str):
        return None
    match = re.match(r"^(\d{2}/\d{2}/\d{4})", value.strip())
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%m/%d/%Y").date()
    except ValueError:
        return None


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def year_before(day):
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # Leap day
        return day.replace(year=day.year - 1, month=2, day=28)


def emit(ready, errors, determinate=False, eligible=None, checks=None, payload=None):
    print(json.dumps({
        "ready": ready,
        "errors": errors,
        "eligibility_determinate": determinate,
        "eligible_for_provisional_credit": eligible,
        "eligibility_checks": checks or {},
        "payload": payload,
    }, sort_keys=True, default=str))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        emit(False, ["stdin must contain one JSON object: %s" % exc])
        return
    if not isinstance(data, dict):
        emit(False, ["input must be a JSON object"])
        return
    dispute = data.get("dispute")
    if not isinstance(dispute, dict):
        emit(False, ["dispute must be an object"])
        return

    errors = []
    required = (
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
        "phone", "email", "address", "purchase_date", "issue_noticed_date",
        "dispute_reason", "resolution_requested",
    )
    for field in required:
        if not isinstance(dispute.get(field), str) or not dispute[field].strip():
            errors.append("missing or invalid required string: %s" % field)
    if not isinstance(dispute.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    if dispute.get("card_action") not in ACTIONS:
        errors.append("card_action is not permitted")
    last4 = dispute.get("card_last_4_digits")
    if isinstance(last4, str) and not re.fullmatch(r"\d{4}", last4):
        errors.append("card_last_4_digits must contain exactly four digits")
    reason = dispute.get("dispute_reason")
    if reason not in REASONS:
        errors.append("dispute_reason is not permitted")
    resolution = dispute.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not permitted")
    partial = dispute.get("partial_refund_amount")
    if resolution == "partial_refund":
        if (amount(partial) is None) or amount(partial) <= 0:
            errors.append("partial_refund_amount must be a positive number for partial_refund")
    elif partial is not None:
        errors.append("partial_refund_amount is only allowed for partial_refund")

    purchase_day = parse_date(dispute.get("purchase_date"))
    noticed_day = parse_date(dispute.get("issue_noticed_date"))
    if purchase_day is None:
        errors.append("purchase_date must use MM/DD/YYYY and be a real date")
    if noticed_day is None:
        errors.append("issue_noticed_date must use MM/DD/YYYY and be a real date")

    current_day = parse_date(data.get("current_date"))
    opened_day = parse_date(data.get("account_open_date"))
    transaction_amount = amount(data.get("transaction_amount"))
    card_type = data.get("card_type")
    prior = data.get("prior_dispute_dates")
    eligibility_inputs_ok = True
    if current_day is None:
        errors.append("current_date is required to determine eligibility")
        eligibility_inputs_ok = False
    if opened_day is None:
        errors.append("account_open_date is required to determine eligibility")
        eligibility_inputs_ok = False
    if transaction_amount is None:
        errors.append("transaction_amount must be a number to determine eligibility")
        eligibility_inputs_ok = False
    if card_type not in LIMITS:
        errors.append("card_type has no known provisional-credit tier limit")
        eligibility_inputs_ok = False
    if not isinstance(prior, list):
        errors.append("prior_dispute_dates must be a list from dispute history")
        eligibility_inputs_ok = False
        prior = []

    prior_days = []
    for index, value in enumerate(prior):
        parsed = parse_date(value)
        if parsed is None:
            errors.append("prior_dispute_dates[%d] is not a valid MM/DD/YYYY date" % index)
            eligibility_inputs_ok = False
        else:
            prior_days.append(parsed)

    eligible = None
    checks = {}
    if eligibility_inputs_ok and purchase_day is not None:
        if current_day < purchase_day:
            errors.append("purchase_date cannot be after current_date")
        if noticed_day is not None and noticed_day < purchase_day:
            errors.append("issue_noticed_date cannot precede purchase_date")
        if opened_day > current_day:
            errors.append("account_open_date cannot be after current_date")

        cutoff = year_before(current_day)
        recent_count = sum(cutoff <= date <= current_day for date in prior_days)
        age_days = (current_day - purchase_day).days
        checks = {
            "account_open_at_least_60_days": (current_day - opened_day).days >= 60,
            "amount_at_least_25": transaction_amount >= Decimal("25"),
            "amount_within_tier_limit": transaction_amount <= LIMITS[card_type],
            "tier_limit": str(LIMITS[card_type]),
            "prior_disputes_last_12_months": recent_count,
            "no_more_than_two_prior_disputes": recent_count <= 2,
            "reason_category_eligible": reason in {
                "unauthorized_fraudulent_charge", "duplicate_charge",
                "goods_services_not_received",
            },
            "goods_not_received_more_than_30_days": (
                reason != "goods_services_not_received" or age_days > 30
            ),
            "merchant_contact_requirement_met": (
                reason == "unauthorized_fraudulent_charge" or
                dispute.get("contacted_merchant") is True
            ),
        }
        eligible = all(value for value in checks.values() if isinstance(value, bool))

    ready = not errors and eligible is not None
    payload = None
    if ready:
        payload = dict(dispute)
        payload["eligible_for_provisional_credit"] = eligible
    emit(ready, errors, eligible is not None, eligible, checks, payload)


if __name__ == "__main__":
    main()
