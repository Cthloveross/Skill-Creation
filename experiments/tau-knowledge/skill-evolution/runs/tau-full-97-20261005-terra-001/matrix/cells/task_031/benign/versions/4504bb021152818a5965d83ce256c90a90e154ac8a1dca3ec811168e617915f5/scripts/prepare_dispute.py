#!/usr/bin/env python3
"""Validate and prepare a credit-card dispute filing payload.

Reads one JSON object from stdin and prints one JSON object. This program does
not call banking tools. See SKILL.md for the input and output schemas.
"""
import json
import math
import sys
from datetime import date, datetime

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
CARD_ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_LIMITS = {
    "Bronze Rewards Card": 2500.00,
    "EcoCard": 2500.00,
    "Business Bronze Rewards Card": 2500.00,
    "Crypto-Cash Back Card": 2500.00,
    "Crypto-Cash Back": 2500.00,
    "Silver Rewards Card": 5000.00,
    "Business Silver Rewards Card": 5000.00,
    "Green Rewards Card": 5000.00,
    "Silver Zoom Card": 5000.00,
    "Gold Rewards Card": 10000.00,
    "Business Gold Rewards Card": 10000.00,
    "Platinum Rewards Card": 15000.00,
    "Business Platinum Rewards Card": 15000.00,
    "Diamond Elite Card": 25000.00,
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a nonempty date string")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError("must be MM/DD/YYYY or an ISO date/timestamp") from exc


def finite_number(value, field, errors):
    if isinstance(value, bool):
        errors.append(f"{field} must be a number, not a boolean")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a number")
        return None
    if not math.isfinite(number):
        errors.append(f"{field} must be finite")
        return None
    return number


def required_text(data, field, errors):
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required and must be a nonempty string")
        return None
    return value.strip()


def main(data):
    errors = []
    text_fields = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name",
        "user_id", "phone", "email", "address", "purchase_date",
        "issue_noticed_date", "dispute_reason", "resolution_requested",
        "card_type", "account_open_date", "current_date",
    ]
    values = {field: required_text(data, field, errors) for field in text_fields}

    if values["card_action"] and values["card_action"] not in CARD_ACTIONS:
        errors.append("card_action is not an allowed value")
    if values["dispute_reason"] and values["dispute_reason"] not in REASONS:
        errors.append("dispute_reason is not an allowed value")
    if values["resolution_requested"] and values["resolution_requested"] not in RESOLUTIONS:
        errors.append("resolution_requested is not an allowed value")
    if values["card_last_4_digits"] and (not values["card_last_4_digits"].isdigit() or len(values["card_last_4_digits"]) != 4):
        errors.append("card_last_4_digits must contain exactly four digits")

    contacted = data.get("contacted_merchant")
    if type(contacted) is not bool:
        errors.append("contacted_merchant must be true or false")

    parsed_dates = {}
    for field in ("purchase_date", "issue_noticed_date", "account_open_date", "current_date"):
        if values[field]:
            try:
                parsed_dates[field] = parse_date(values[field])
            except ValueError as exc:
                errors.append(f"{field} {exc}")
    for field in ("purchase_date", "issue_noticed_date", "account_open_date"):
        if values[field] and field in parsed_dates and "/" not in values[field]:
            errors.append(f"{field} must use MM/DD/YYYY format")

    amount = finite_number(data.get("transaction_amount"), "transaction_amount", errors)
    if amount is not None and amount < 0:
        errors.append("transaction_amount must not be negative")
    count = data.get("prior_disputes_past_12_months")
    if type(count) is not int or count < 0:
        errors.append("prior_disputes_past_12_months must be a nonnegative integer")

    partial = data.get("partial_refund_amount")
    if values["resolution_requested"] == "partial_refund":
        partial = finite_number(partial, "partial_refund_amount", errors)
        if partial is not None and partial <= 0:
            errors.append("partial_refund_amount must be greater than zero")
    elif partial is not None:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")

    eligibility = {"eligible": None, "conditions": {}, "reasons": []}
    eligibility_inputs_ok = not any(
        message.startswith(prefix) for message in errors for prefix in (
            "transaction_amount", "prior_disputes_past_12_months", "account_open_date", "current_date", "purchase_date", "card_type", "contacted_merchant", "dispute_reason"
        )
    )
    if eligibility_inputs_ok and all(k in parsed_dates for k in ("purchase_date", "account_open_date", "current_date")) and amount is not None:
        reason = values["dispute_reason"]
        limit = TIER_LIMITS.get(values["card_type"])
        if limit is None:
            errors.append("card_type does not map to a provisional-credit tier")
        else:
            account_age = (parsed_dates["current_date"] - parsed_dates["account_open_date"]).days
            purchase_age = (parsed_dates["current_date"] - parsed_dates["purchase_date"]).days
            reason_ok = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
            delivery_age_ok = reason != "goods_services_not_received" or purchase_age > 30
            merchant_ok = reason == "unauthorized_fraudulent_charge" or contacted is True
            conditions = {
                "account_open_at_least_60_days": account_age >= 60,
                "eligible_reason": reason_ok,
                "goods_not_received_purchase_more_than_30_days_ago": delivery_age_ok,
                "amount_at_least_25": amount >= 25.00,
                "amount_within_card_tier_limit": amount <= limit,
                "no_more_than_2_prior_disputes": count <= 2,
                "merchant_contact_requirement_met": merchant_ok,
            }
            eligibility["conditions"] = conditions
            eligibility["eligible"] = all(conditions.values())
            eligibility["tier_limit"] = limit
            if not eligibility["eligible"]:
                eligibility["reasons"] = [key for key, passed in conditions.items() if not passed]

    # A valid filing requires a fully determined boolean eligibility result.
    if eligibility["eligible"] is None:
        errors.append("provisional-credit eligibility could not be determined from supplied inputs")

    payload = None
    if not errors:
        payload = {
            "transaction_id": values["transaction_id"],
            "card_action": values["card_action"],
            "card_last_4_digits": values["card_last_4_digits"],
            "full_name": values["full_name"],
            "user_id": values["user_id"],
            "phone": values["phone"],
            "email": values["email"],
            "address": values["address"],
            "contacted_merchant": contacted,
            "purchase_date": values["purchase_date"],
            "issue_noticed_date": values["issue_noticed_date"],
            "dispute_reason": values["dispute_reason"],
            "resolution_requested": values["resolution_requested"],
            "eligible_for_provisional_credit": eligibility["eligible"],
        }
        if values["resolution_requested"] == "partial_refund":
            payload["partial_refund_amount"] = partial

    return {"ready": payload is not None, "errors": errors, "eligibility": eligibility, "payload": payload}


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(supplied), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ready": False, "errors": [str(exc)], "eligibility": {"eligible": None}, "payload": None}, separators=(",", ":")))
