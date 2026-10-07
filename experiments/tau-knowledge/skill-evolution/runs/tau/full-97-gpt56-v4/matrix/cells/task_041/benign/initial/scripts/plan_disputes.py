#!/usr/bin/env python3
"""Validate dispute records and calculate provisional-credit eligibility.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the input schema. This program makes no network calls and performs no bank action.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
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
    "Bronze Rewards Card": Decimal("2500.00"),
    "EcoCard": Decimal("2500.00"),
    "Business Bronze Rewards Card": Decimal("2500.00"),
    "Crypto-Cash Back Card": Decimal("2500.00"),
    "Silver Rewards Card": Decimal("5000.00"),
    "Business Silver Rewards Card": Decimal("5000.00"),
    "Green Rewards Card": Decimal("5000.00"),
    "Silver Zoom Card": Decimal("5000.00"),
    "Gold Rewards Card": Decimal("10000.00"),
    "Business Gold Rewards Card": Decimal("10000.00"),
    "Platinum Rewards Card": Decimal("15000.00"),
    "Business Platinum Rewards Card": Decimal("15000.00"),
    "Diamond Elite Card": Decimal("25000.00"),
}


def date_value(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be an MM/DD/YYYY string")
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        errors.append(f"{field} must use MM/DD/YYYY")
        return None


def money(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def required_string(obj, field, errors):
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} is required")
        return None
    return value


def build_case(case, customer, as_of, prior_count, index):
    errors = []
    prefix = f"cases[{index}]"
    for field in ("transaction_id", "card_type", "card_last_4_digits"):
        required_string(case, field, errors)
    card_last4 = case.get("card_last_4_digits")
    if isinstance(card_last4, str) and card_last4 and (len(card_last4) != 4 or not card_last4.isdigit()):
        errors.append("card_last_4_digits must be exactly four digits")
    purchase = date_value(case.get("purchase_date"), "purchase_date", errors)
    noticed = date_value(case.get("issue_noticed_date"), "issue_noticed_date", errors)
    opened = date_value(case.get("account_open_date"), "account_open_date", errors)
    amount = money(case.get("amount"), "amount", errors)
    reason = case.get("dispute_reason")
    resolution = case.get("resolution_requested")
    action = case.get("card_action")
    contacted = case.get("contacted_merchant")
    if reason not in REASONS:
        errors.append("dispute_reason is not a permitted value")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is not a permitted value")
    if action not in ACTIONS:
        errors.append("card_action is not a permitted value")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")
    if resolution == "partial_refund":
        partial = money(case.get("partial_refund_amount"), "partial_refund_amount", errors)
        if partial is not None and partial <= 0:
            errors.append("partial_refund_amount must be greater than zero")
        if partial is not None and amount is not None and partial > amount:
            errors.append("partial_refund_amount cannot exceed amount")
    elif "partial_refund_amount" in case:
        errors.append("partial_refund_amount is allowed only for partial_refund")
    if purchase and purchase > as_of:
        errors.append("purchase_date cannot be after as_of_date")
    if noticed and noticed > as_of:
        errors.append("issue_noticed_date cannot be after as_of_date")

    eligibility_reasons = []
    eligible = True
    if opened is None or (as_of - opened).days < 60:
        eligible = False
        eligibility_reasons.append("account has not been open at least 60 days")
    if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
        eligible = False
        eligibility_reasons.append("dispute reason is not eligible")
    if reason == "goods_services_not_received":
        if purchase is None or (as_of - purchase).days <= 30:
            eligible = False
            eligibility_reasons.append("goods/services-not-received purchase is not more than 30 days old")
    cap = TIER_CAPS.get(case.get("card_type"))
    if cap is None:
        eligible = False
        eligibility_reasons.append("card type has no recognized provisional-credit limit")
    if amount is None or amount < Decimal("25.00"):
        eligible = False
        eligibility_reasons.append("transaction amount is below $25.00 or invalid")
    elif cap is not None and amount > cap:
        eligible = False
        eligibility_reasons.append("transaction amount exceeds card-tier limit")
    if prior_count > 2:
        eligible = False
        eligibility_reasons.append("more than 2 previous disputes in the past 12 months")
    if reason != "unauthorized_fraudulent_charge" and contacted is not True:
        eligible = False
        eligibility_reasons.append("merchant was not contacted for a non-fraud dispute")
    if eligible:
        eligibility_reasons.append("all provisional-credit conditions are satisfied")

    payload = {
        "transaction_id": case.get("transaction_id"),
        "card_action": action,
        "card_last_4_digits": case.get("card_last_4_digits"),
        "full_name": customer.get("full_name"),
        "user_id": customer.get("user_id"),
        "phone": customer.get("phone"),
        "email": customer.get("email"),
        "address": customer.get("address"),
        "contacted_merchant": contacted,
        "purchase_date": case.get("purchase_date"),
        "issue_noticed_date": case.get("issue_noticed_date"),
        "dispute_reason": reason,
        "resolution_requested": resolution,
        "eligible_for_provisional_credit": eligible,
    }
    if resolution == "partial_refund":
        payload["partial_refund_amount"] = float(case.get("partial_refund_amount")) if isinstance(case.get("partial_refund_amount"), (int, float)) else case.get("partial_refund_amount")
    return {"index": index, "valid": not errors, "errors": [f"{prefix}: {e}" for e in errors], "eligibility_reasons": eligibility_reasons, "payload": payload}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc.msg}"], "plans": []}))
        return
    errors = []
    if not isinstance(data, dict):
        print(json.dumps({"valid": False, "errors": ["top-level input must be an object"], "plans": []}))
        return
    as_of = date_value(data.get("as_of_date"), "as_of_date", errors)
    prior = data.get("previous_disputes_last_12_months")
    if not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        errors.append("previous_disputes_last_12_months must be a nonnegative integer")
        prior = 0
    customer = data.get("customer")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
        customer = {}
    for field in ("full_name", "user_id", "phone", "email", "address"):
        required_string(customer, f"customer.{field}", errors)
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append("cases must be a nonempty array")
        cases = []
    if as_of is None:
        print(json.dumps({"valid": False, "errors": errors, "plans": []}, indent=2))
        return
    plans = []
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"cases[{i}] must be an object")
            continue
        plans.append(build_case(case, customer, as_of, prior, i))
    errors.extend(error for plan in plans for error in plan["errors"])
    print(json.dumps({"valid": not errors, "errors": errors, "plans": plans}, indent=2))


if __name__ == "__main__":
    main()
