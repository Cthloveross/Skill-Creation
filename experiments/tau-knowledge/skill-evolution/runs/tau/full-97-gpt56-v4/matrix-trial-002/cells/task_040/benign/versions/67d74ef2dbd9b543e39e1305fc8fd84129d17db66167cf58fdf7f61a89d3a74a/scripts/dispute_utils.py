#!/usr/bin/env python3
"""Validate dispute payloads and evaluate provisional-credit eligibility.

Reads one JSON object from stdin and emits one JSON object. Uses only the
standard library so it can run in the packaged Skill runtime.
"""
import json
import sys
from datetime import datetime

DATE_FORMAT = "%m/%d/%Y"
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
    "Bronze Rewards Card": 2500.0,
    "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0,
    "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0,
    "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0,
    "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0,
    "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0,
    "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a MM/DD/YYYY string")
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).date()
    except ValueError:
        errors.append(f"{field} must use MM/DD/YYYY")
        return None


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def eligibility(data):
    errors = []
    opened = parse_date(data.get("account_open_date"), "account_open_date", errors)
    purchase = parse_date(data.get("purchase_date"), "purchase_date", errors)
    evaluated = parse_date(data.get("evaluation_date"), "evaluation_date", errors)
    amount = data.get("amount")
    reason = data.get("dispute_reason")
    card_type = data.get("card_type")
    prior = data.get("prior_disputes_12_months")
    contacted = data.get("contacted_merchant")
    failed = []

    if errors:
        return {"eligible_for_provisional_credit": False, "failed_conditions": errors}
    if not is_number(amount) or amount < 0:
        return {"eligible_for_provisional_credit": False,
                "failed_conditions": ["amount must be a nonnegative number"]}
    if not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        return {"eligible_for_provisional_credit": False,
                "failed_conditions": ["prior_disputes_12_months must be a nonnegative integer"]}
    if not isinstance(contacted, bool):
        return {"eligible_for_provisional_credit": False,
                "failed_conditions": ["contacted_merchant must be boolean"]}
    if card_type not in TIER_LIMITS:
        return {"eligible_for_provisional_credit": False,
                "failed_conditions": ["unrecognized card type/tier"]}
    if reason not in REASONS:
        return {"eligible_for_provisional_credit": False,
                "failed_conditions": ["unrecognized dispute reason"]}
    if purchase > evaluated:
        failed.append("purchase date is after evaluation date")
    if (evaluated - opened).days < 60:
        failed.append("account has been open fewer than 60 days")
    allowed_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
    if reason == "goods_services_not_received":
        if (evaluated - purchase).days > 30:
            allowed_reason = True
        else:
            failed.append("goods/services-not-received purchase is not more than 30 days old")
    if not allowed_reason and reason != "goods_services_not_received":
        failed.append("dispute reason is not eligible")
    if amount < 25.0:
        failed.append("transaction amount is under $25.00")
    if amount > TIER_LIMITS[card_type]:
        failed.append("transaction amount exceeds the card tier limit")
    if prior > 2:
        failed.append("more than two prior disputes in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and not contacted:
        failed.append("merchant was not contacted for a non-fraud dispute")
    return {"eligible_for_provisional_credit": not failed, "failed_conditions": failed}


def validate_payload(payload):
    errors = []
    required_strings = [
        "transaction_id", "card_last_4_digits", "full_name", "user_id", "phone",
        "email", "address",
    ]
    for key in required_strings:
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            errors.append(f"{key} must be a nonempty string")
    if payload.get("card_action") not in ACTIONS:
        errors.append("card_action is invalid")
    if not isinstance(payload.get("contacted_merchant"), bool):
        errors.append("contacted_merchant must be boolean")
    if not isinstance(payload.get("eligible_for_provisional_credit"), bool):
        errors.append("eligible_for_provisional_credit must be boolean")
    parse_date(payload.get("purchase_date"), "purchase_date", errors)
    parse_date(payload.get("issue_noticed_date"), "issue_noticed_date", errors)
    if payload.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is invalid")
    resolution = payload.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is invalid")
    partial_present = "partial_refund_amount" in payload
    if resolution == "partial_refund":
        value = payload.get("partial_refund_amount")
        if not is_number(value) or value <= 0:
            errors.append("partial_refund_amount must be a positive number for partial_refund")
    elif partial_present:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")
    return {"valid": not errors, "errors": errors}


def main():
    try:
        request = json.load(sys.stdin)
        action = request.get("action")
        if action == "eligibility":
            result = eligibility(request)
        elif action == "validate_payload":
            payload = request.get("payload")
            if not isinstance(payload, dict):
                result = {"valid": False, "errors": ["payload must be an object"]}
            else:
                result = validate_payload(payload)
        else:
            result = {"error": "action must be eligibility or validate_payload"}
    except json.JSONDecodeError:
        result = {"error": "stdin must contain one JSON object"}
    except Exception as exc:
        result = {"error": f"unable to process input: {exc}"}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
