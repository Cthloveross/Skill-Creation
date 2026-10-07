#!/usr/bin/env python3
"""Validate a credit-card dispute payload and calculate provisional eligibility.

Read one JSON object from stdin and emit one JSON object to stdout.  This module is
purely deterministic: it does not contact banking systems or submit actions.
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
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_CAPS = {
    "entry": Decimal("2500"),
    "mid": Decimal("5000"),
    "premium": Decimal("10000"),
    "elite": Decimal("15000"),
    "invitation": Decimal("25000"),
}
# Card product aliases make the helper useful with account lookup descriptions.
PRODUCT_TIERS = {
    "bronze rewards card": "entry", "ecocard": "entry",
    "business bronze rewards card": "entry", "crypto-cash back card": "entry",
    "silver rewards card": "mid", "business silver rewards card": "mid",
    "green rewards card": "mid", "silver zoom card": "mid",
    "gold rewards card": "premium", "business gold rewards card": "premium",
    "platinum rewards card": "elite", "business platinum rewards card": "elite",
    "diamond elite card": "invitation",
}


def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be a MM/DD/YYYY string")
    return datetime.strptime(value, "%m/%d/%Y").date()


def decimal_value(value):
    if isinstance(value, bool):
        raise InvalidOperation
    result = Decimal(str(value))
    if not result.is_finite():
        raise InvalidOperation
    return result


def tier_key(value):
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if text in TIER_CAPS:
        return text
    return PRODUCT_TIERS.get(text)


def validate(payload, context):
    if not isinstance(payload, dict):
        return {"valid": False, "errors": ["payload must be an object"], "payload": {}}
    errors = []
    required_strings = [
        "transaction_id", "card_action", "card_last_4_digits", "full_name",
        "user_id", "phone", "email", "address", "purchase_date",
        "issue_noticed_date", "dispute_reason", "resolution_requested",
    ]
    for field in required_strings:
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"{field} is required and must be a nonempty string")
    if payload.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    if payload.get("dispute_reason") not in REASONS:
        errors.append("dispute_reason is not a permitted value")
    if payload.get("resolution_requested") not in RESOLUTIONS:
        errors.append("resolution_requested is not a permitted value")
    for field in ("contacted_merchant", "eligible_for_provisional_credit"):
        if not isinstance(payload.get(field), bool):
            errors.append(f"{field} must be boolean")
    for field in ("purchase_date", "issue_noticed_date"):
        if field in payload and isinstance(payload[field], str):
            try:
                parse_date(payload[field])
            except ValueError:
                errors.append(f"{field} must use MM/DD/YYYY")
    partial_present = "partial_refund_amount" in payload and payload.get("partial_refund_amount") is not None
    if payload.get("resolution_requested") == "partial_refund":
        if not partial_present:
            errors.append("partial_refund_amount is required for partial_refund")
        else:
            try:
                partial = decimal_value(payload["partial_refund_amount"])
                if partial <= 0:
                    errors.append("partial_refund_amount must be greater than zero")
                if "transaction_amount" in context:
                    amount = decimal_value(context["transaction_amount"])
                    if partial > amount:
                        errors.append("partial_refund_amount cannot exceed transaction_amount")
            except (InvalidOperation, ValueError):
                errors.append("partial_refund_amount must be numeric")
    elif partial_present:
        errors.append("partial_refund_amount must be omitted unless resolution_requested is partial_refund")
    return {"valid": not errors, "errors": errors, "payload": payload}


def eligibility(payload, context):
    reasons = []
    diagnostics = {}
    try:
        today = parse_date(context.get("current_date"))
    except ValueError:
        return {"eligible": False, "reasons": ["current_date is missing or invalid"], "diagnostics": {}}
    try:
        opened = parse_date(context.get("account_open_date"))
        account_age = (today - opened).days
        diagnostics["account_age_days"] = account_age
        if account_age < 60:
            reasons.append("account is less than 60 days old")
    except ValueError:
        reasons.append("account_open_date is missing or invalid")
    reason = payload.get("dispute_reason")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        reasons.append("dispute reason does not qualify")
    if reason == "goods_services_not_received":
        purchase_value = context.get("purchase_date", payload.get("purchase_date"))
        try:
            purchase_age = (today - parse_date(purchase_value)).days
            diagnostics["purchase_age_days"] = purchase_age
            if purchase_age <= 30:
                reasons.append("goods/services-not-received purchase is not more than 30 days old")
        except ValueError:
            reasons.append("purchase_date is missing or invalid")
    try:
        amount = decimal_value(context.get("transaction_amount"))
        diagnostics["transaction_amount"] = str(amount)
        if amount < Decimal("25"):
            reasons.append("transaction amount is below $25")
        tier = tier_key(context.get("card_tier"))
        if tier is None:
            reasons.append("card_tier is missing or unsupported")
        else:
            diagnostics["tier"] = tier
            diagnostics["tier_cap"] = str(TIER_CAPS[tier])
            if amount > TIER_CAPS[tier]:
                reasons.append("transaction amount exceeds the tier provisional-credit cap")
    except (InvalidOperation, ValueError, TypeError):
        reasons.append("transaction_amount is missing or invalid")
    history = context.get("previous_dispute_dates", [])
    if not isinstance(history, list):
        reasons.append("previous_dispute_dates must be a list")
    else:
        count = 0
        malformed = False
        for item in history:
            try:
                filed = parse_date(item)
                age = (today - filed).days
                if 0 <= age <= 365:
                    count += 1
            except ValueError:
                malformed = True
        diagnostics["previous_disputes_last_12_months"] = count
        if malformed:
            reasons.append("one or more previous dispute dates are invalid")
        if count > 2:
            reasons.append("more than two previous disputes were filed in the last 12 months")
    if reason != "unauthorized_fraudulent_charge" and payload.get("contacted_merchant") is not True:
        reasons.append("merchant was not contacted for a non-fraud dispute")
    return {"eligible": not reasons, "reasons": reasons, "diagnostics": diagnostics}


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        action = request.get("action")
        payload = request.get("payload", {})
        context = request.get("context", {})
        if not isinstance(context, dict):
            raise ValueError("context must be an object")
        if action == "validate":
            result = validate(payload, context)
        elif action == "eligibility":
            result = eligibility(payload, context)
        else:
            result = {"error": "action must be validate or eligibility"}
    except Exception as exc:
        result = {"error": str(exc)}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
