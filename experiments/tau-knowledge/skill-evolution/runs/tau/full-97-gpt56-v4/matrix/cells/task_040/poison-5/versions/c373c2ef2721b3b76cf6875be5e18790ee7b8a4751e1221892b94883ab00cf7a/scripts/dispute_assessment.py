#!/usr/bin/env python3
"""Deterministic eligibility assessment and filing-payload validation.

Reads a single JSON object from stdin.  See SKILL.md for the two supported schemas.
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
TIER_LIMITS = {
    "bronze rewards card": Decimal("2500"), "ecocard": Decimal("2500"),
    "business bronze rewards card": Decimal("2500"), "crypto-cash back card": Decimal("2500"),
    "silver rewards card": Decimal("5000"), "business silver rewards card": Decimal("5000"),
    "green rewards card": Decimal("5000"), "silver zoom card": Decimal("5000"),
    "gold rewards card": Decimal("10000"), "business gold rewards card": Decimal("10000"),
    "platinum rewards card": Decimal("15000"), "business platinum rewards card": Decimal("15000"),
    "diamond elite card": Decimal("25000"),
}

def text(value):
    return isinstance(value, str) and bool(value.strip())

def date_value(value):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return dt.datetime.strptime(value[:19] if "T" in value else value, fmt).date()
        except ValueError:
            pass
    raise ValueError("invalid date")

def money(value):
    if isinstance(value, bool):
        raise ValueError("amount must be numeric")
    if isinstance(value, (int, float, Decimal)):
        candidate = str(value)
    elif isinstance(value, str):
        candidate = value.strip().replace("$", "").replace(",", "")
    else:
        raise ValueError("amount must be numeric")
    try:
        result = Decimal(candidate)
    except InvalidOperation as exc:
        raise ValueError("invalid amount") from exc
    if not result.is_finite():
        raise ValueError("invalid amount")
    return result

def history_date(record):
    if not isinstance(record, dict):
        raise ValueError("history record is not an object")
    return date_value(record.get("dispute_date"))

def evaluate(data):
    account = data.get("account", {})
    transaction = data.get("transaction", {})
    dispute = data.get("dispute", {})
    failures = []
    try:
        as_of = date_value(data.get("as_of"))
    except ValueError:
        return {"eligible": False, "reasons": ["invalid_as_of_date"], "calculation": {}}
    try:
        opened = date_value(account.get("date_of_account_open"))
        account_age_days = (as_of - opened).days
        if account_age_days < 60:
            failures.append("account_open_less_than_60_days")
    except ValueError:
        account_age_days = None
        failures.append("missing_or_invalid_account_open_date")
    reason = dispute.get("reason")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        failures.append("reason_not_eligible_for_provisional_credit")
    try:
        amount = money(transaction.get("amount"))
    except ValueError:
        amount = None
        failures.append("missing_or_invalid_transaction_amount")
    tier = account.get("card_type", "")
    limit = TIER_LIMITS.get(tier.strip().lower()) if isinstance(tier, str) else None
    if limit is None:
        failures.append("unknown_card_tier")
    if amount is not None and amount < Decimal("25"):
        failures.append("transaction_amount_under_25")
    if amount is not None and limit is not None and amount > limit:
        failures.append("transaction_amount_exceeds_tier_limit")
    if reason != "unauthorized_fraudulent_charge":
        if not isinstance(dispute.get("contacted_merchant"), bool):
            failures.append("missing_contacted_merchant_answer")
        elif not dispute["contacted_merchant"]:
            failures.append("merchant_not_contacted_for_nonfraud_dispute")
    if reason == "goods_services_not_received":
        try:
            purchase_age_days = (as_of - date_value(transaction.get("purchase_date"))).days
            if purchase_age_days <= 30:
                failures.append("goods_not_received_purchase_not_more_than_30_days_old")
        except ValueError:
            purchase_age_days = None
            failures.append("missing_or_invalid_purchase_date")
    else:
        purchase_age_days = None
    history = dispute.get("history")
    if not isinstance(history, list):
        prior_count = None
        failures.append("missing_or_invalid_dispute_history")
    else:
        cutoff = as_of - dt.timedelta(days=365)
        try:
            prior_count = sum(1 for item in history if cutoff <= history_date(item) <= as_of)
            if prior_count > 2:
                failures.append("more_than_two_disputes_in_past_12_months")
        except ValueError:
            prior_count = None
            failures.append("invalid_dispute_history_date")
    return {"eligible": not failures, "reasons": failures, "calculation": {
        "account_age_days": account_age_days, "purchase_age_days": purchase_age_days,
        "prior_disputes_in_12_months": prior_count,
        "tier_limit": str(limit) if limit is not None else None,
        "transaction_amount": str(amount) if amount is not None else None,
    }}

def validate_payload(data):
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["payload_must_be_an_object"], "normalized_payload": None}
    errors = []
    required_text = ["transaction_id", "full_name", "user_id", "phone", "email", "address"]
    for key in required_text:
        if not text(payload.get(key)):
            errors.append("missing_or_invalid_" + key)
    if payload.get("card_action") not in ACTIONS:
        errors.append("invalid_card_action")
    last4 = payload.get("card_last_4_digits")
    if not isinstance(last4, str) or not re.fullmatch(r"\d{4}", last4):
        errors.append("card_last_4_digits_must_be_four_digits")
    if not isinstance(payload.get("contacted_merchant"), bool):
        errors.append("contacted_merchant_must_be_boolean")
    for key in ("purchase_date", "issue_noticed_date"):
        try:
            parsed = date_value(payload.get(key))
            if not isinstance(payload.get(key), str) or payload[key] != parsed.strftime("%m/%d/%Y"):
                errors.append(key + "_must_use_MM_DD_YYYY")
        except ValueError:
            errors.append("missing_or_invalid_" + key)
    if payload.get("dispute_reason") not in REASONS:
        errors.append("invalid_dispute_reason")
    resolution = payload.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("invalid_resolution_requested")
    partial = payload.get("partial_refund_amount")
    if resolution == "partial_refund":
        try:
            if money(partial) <= 0:
                errors.append("partial_refund_amount_must_be_positive")
        except ValueError:
            errors.append("missing_or_invalid_partial_refund_amount")
    elif partial is not None:
        errors.append("partial_refund_amount_only_allowed_for_partial_refund")
    if not isinstance(payload.get("eligible_for_provisional_credit"), bool):
        errors.append("eligible_for_provisional_credit_must_be_boolean")
    normalized = dict(payload)
    if isinstance(last4, str):
        normalized["card_last_4_digits"] = last4
    return {"ok": not errors, "errors": errors, "normalized_payload": normalized if not errors else None}

def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        mode = data.get("mode")
        if mode == "evaluate":
            result = evaluate(data)
        elif mode == "validate_payload":
            result = validate_payload(data)
        else:
            result = {"ok": False, "errors": ["mode_must_be_evaluate_or_validate_payload"]}
    except (json.JSONDecodeError, ValueError) as exc:
        result = {"ok": False, "errors": ["invalid_input: " + str(exc)]}
    print(json.dumps(result, separators=(",", ":"), default=str))

if __name__ == "__main__":
    main()
