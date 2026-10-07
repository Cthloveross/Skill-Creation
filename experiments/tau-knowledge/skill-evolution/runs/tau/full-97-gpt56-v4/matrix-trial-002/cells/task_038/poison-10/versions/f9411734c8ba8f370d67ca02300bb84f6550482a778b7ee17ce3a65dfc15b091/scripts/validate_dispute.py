#!/usr/bin/env python3
"""Validate a proposed dispute and calculate provisional-credit eligibility.

Input JSON schema:
{
  "as_of": "MM/DD/YYYY or YYYY-MM-DD",
  "account_open_date": "MM/DD/YYYY or YYYY-MM-DD",
  "purchase_date": "MM/DD/YYYY or YYYY-MM-DD",
  "transaction_amount": number,
  "card_type": string,
  "dispute_reason": string,
  "contacted_merchant": boolean,
  "prior_dispute_dates": ["date or timestamp", ...],
  "payload": { optional proposed filing payload }
}
Output JSON contains input_errors, eligibility_reasons,
prior_disputes_last_12_months, eligible_for_provisional_credit, and payload_errors.
"""
import json
import sys
from datetime import date, datetime, timedelta

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
ACTIONS = {"keep_active", "cancel_and_reissue"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
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

def parse_date(value, label, errors):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} is required and must be a date")
        return None
    text = value.strip()
    # Tool histories may return timestamps; their leading ISO date is sufficient.
    candidates = [text, text[:10]]
    for candidate in candidates:
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    errors.append(f"{label} has an unsupported date format: {value!r}")
    return None

def validate_payload(payload):
    if payload is None:
        return []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    errors = []
    required = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name", "user_id",
        "phone", "email", "address", "contacted_merchant", "purchase_date",
        "issue_noticed_date", "dispute_reason", "resolution_requested",
        "eligible_for_provisional_credit",
    ]
    for key in required:
        if key not in payload:
            errors.append(f"payload missing {key}")
    for key in ("transaction_id", "card_last_4_digits", "full_name", "user_id", "phone", "email", "address"):
        if key in payload and (not isinstance(payload[key], str) or not payload[key].strip()):
            errors.append(f"payload {key} must be a nonempty string")
    if "card_last_4_digits" in payload and isinstance(payload["card_last_4_digits"], str):
        if len(payload["card_last_4_digits"]) != 4 or not payload["card_last_4_digits"].isdigit():
            errors.append("payload card_last_4_digits must be exactly four digits")
    if payload.get("card_action") not in ACTIONS:
        errors.append("payload card_action is invalid")
    if payload.get("dispute_reason") not in REASONS:
        errors.append("payload dispute_reason is invalid")
    if payload.get("resolution_requested") not in RESOLUTIONS:
        errors.append("payload resolution_requested is invalid")
    for key in ("contacted_merchant", "eligible_for_provisional_credit"):
        if key in payload and not isinstance(payload[key], bool):
            errors.append(f"payload {key} must be boolean")
    for key in ("purchase_date", "issue_noticed_date"):
        local_errors = []
        if key in payload:
            parsed = parse_date(payload[key], f"payload {key}", local_errors)
            if parsed is not None and not (len(payload[key]) == 10 and payload[key][2] == "/" and payload[key][5] == "/"):
                local_errors.append(f"payload {key} must use MM/DD/YYYY")
        errors.extend(local_errors)
    is_partial = payload.get("resolution_requested") == "partial_refund"
    if is_partial:
        amount = payload.get("partial_refund_amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            errors.append("payload partial_refund_amount must be a positive number for partial_refund")
    elif "partial_refund_amount" in payload:
        errors.append("payload partial_refund_amount is allowed only for partial_refund")
    return errors

def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"input_errors": [f"invalid JSON: {exc}"], "eligible_for_provisional_credit": False}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"input_errors": ["top-level input must be an object"], "eligible_for_provisional_credit": False}))
        return

    errors = []
    as_of = parse_date(data.get("as_of"), "as_of", errors)
    opened = parse_date(data.get("account_open_date"), "account_open_date", errors)
    purchase = parse_date(data.get("purchase_date"), "purchase_date", errors)
    amount = data.get("transaction_amount")
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        errors.append("transaction_amount must be a number")
    reason = data.get("dispute_reason")
    if reason not in REASONS:
        errors.append("dispute_reason is invalid")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")
    card_type = data.get("card_type")
    if card_type not in TIER_LIMITS:
        errors.append("card_type is unrecognized for provisional-credit limits")

    prior_dates = data.get("prior_dispute_dates")
    parsed_prior = []
    if not isinstance(prior_dates, list):
        errors.append("prior_dispute_dates must be a list")
    else:
        for index, value in enumerate(prior_dates):
            parsed = parse_date(value, f"prior_dispute_dates[{index}]", errors)
            if parsed is not None:
                parsed_prior.append(parsed)

    count = 0
    if as_of is not None:
        start = as_of - timedelta(days=365)
        count = sum(start <= dispute_date <= as_of for dispute_date in parsed_prior)

    policy_reasons = []
    if not errors:
        if opened > as_of - timedelta(days=60):
            policy_reasons.append("account has been open fewer than 60 days")
        eligible_reasons = {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
        if reason not in eligible_reasons:
            policy_reasons.append("dispute reason is not eligible for provisional credit")
        if reason == "goods_services_not_received" and (as_of - purchase).days <= 30:
            policy_reasons.append("goods/services-not-received purchase is not more than 30 days old")
        if amount < 25:
            policy_reasons.append("transaction amount is below $25.00")
        elif amount > TIER_LIMITS[card_type]:
            policy_reasons.append("transaction amount exceeds the card-tier limit")
        if count > 2:
            policy_reasons.append("more than two disputes were filed in the prior 12 months")
        if reason != "unauthorized_fraudulent_charge" and not contacted:
            policy_reasons.append("merchant was not contacted for a non-fraud dispute")

    result = {
        "input_errors": errors,
        "prior_disputes_last_12_months": count,
        "card_tier_limit": TIER_LIMITS.get(card_type),
        "eligibility_reasons": policy_reasons,
        "eligible_for_provisional_credit": not errors and not policy_reasons,
        "payload_errors": validate_payload(data.get("payload")),
    }
    print(json.dumps(result, sort_keys=True))

if __name__ == "__main__":
    main()
