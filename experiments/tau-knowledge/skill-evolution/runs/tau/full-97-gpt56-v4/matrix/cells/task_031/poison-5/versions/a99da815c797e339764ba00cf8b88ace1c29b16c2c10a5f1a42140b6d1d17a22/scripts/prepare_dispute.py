#!/usr/bin/env python3
"""Validate a normalized credit-card dispute and produce tool arguments.
Reads one JSON object from stdin and emits one JSON object to stdout. This script
performs no bank action and never reads customer data from files or services.
"""
import json
import re
import sys
from datetime import datetime, date, timedelta

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIER_LIMITS = {
    "Bronze Rewards Card": 2500.0, "EcoCard": 2500.0,
    "Business Bronze Rewards Card": 2500.0, "Crypto-Cash Back Card": 2500.0,
    "Silver Rewards Card": 5000.0, "Business Silver Rewards Card": 5000.0,
    "Green Rewards Card": 5000.0, "Silver Zoom Card": 5000.0,
    "Gold Rewards Card": 10000.0, "Business Gold Rewards Card": 10000.0,
    "Platinum Rewards Card": 15000.0, "Business Platinum Rewards Card": 15000.0,
    "Diamond Elite Card": 25000.0,
}


def parse_date(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be a date string")
        return None
    value = value.strip()
    candidates = ["%m/%d/%Y"]
    if field == "current_date":
        value = value[:10]
        candidates.append("%Y-%m-%d")
    for fmt in candidates:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    errors.append(f"{field} must use MM/DD/YYYY" + (" or ISO YYYY-MM-DD" if field == "current_date" else ""))
    return None


def nonempty(mapping, key, errors):
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"missing {key}")
        return None
    return value.strip()


def main(data):
    errors = []
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    transaction = data.get("transaction") if isinstance(data.get("transaction"), dict) else {}
    account = data.get("account") if isinstance(data.get("account"), dict) else {}

    full_name = nonempty(customer, "full_name", errors)
    user_id = nonempty(customer, "user_id", errors)
    phone = nonempty(customer, "phone", errors)
    email = nonempty(customer, "email", errors)
    address = nonempty(customer, "address", errors)
    transaction_id = nonempty(transaction, "transaction_id", errors)
    last4 = nonempty(data, "card_last_4_digits", errors)
    if last4 is not None and not re.fullmatch(r"\d{4}", last4):
        errors.append("card_last_4_digits must be exactly four digits returned for the selected card")

    purchase = parse_date(transaction.get("purchase_date"), "purchase_date", errors)
    noticed = parse_date(data.get("issue_noticed_date"), "issue_noticed_date", errors)
    today = parse_date(data.get("current_date"), "current_date", errors)
    opened = parse_date(account.get("opened_date"), "opened_date", errors)
    try:
        amount = float(transaction.get("amount"))
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        amount = None
        errors.append("transaction.amount must be a positive number")

    action = data.get("card_action")
    if action not in ACTIONS:
        errors.append("card_action is invalid")
    contacted = data.get("contacted_merchant")
    if not isinstance(contacted, bool):
        errors.append("contacted_merchant must be boolean")
    reason = data.get("dispute_reason")
    if reason not in REASONS:
        errors.append("dispute_reason is invalid")
    resolution = data.get("resolution_requested")
    if resolution not in RESOLUTIONS:
        errors.append("resolution_requested is invalid")

    partial = data.get("partial_refund_amount")
    if resolution == "partial_refund":
        try:
            partial = float(partial)
            if partial <= 0 or (amount is not None and partial >= amount):
                raise ValueError
        except (TypeError, ValueError):
            errors.append("partial_refund_amount must be positive and less than the transaction amount")
    elif partial is not None:
        errors.append("partial_refund_amount is permitted only for partial_refund")

    transaction_card = transaction.get("card_type")
    account_card = account.get("card_type")
    if not isinstance(transaction_card, str) or not transaction_card:
        errors.append("missing transaction.card_type")
    if not isinstance(account_card, str) or not account_card:
        errors.append("missing account.card_type")
    if transaction_card and account_card and transaction_card != account_card:
        errors.append("selected account card_type does not match transaction card_type")

    # Count dated history entries in the 12 months before (and including) today.
    history_count = 0
    history = data.get("history")
    if not isinstance(history, list):
        errors.append("history must be a list returned by dispute-history lookup")
    elif today:
        for index, record in enumerate(history):
            if not isinstance(record, dict):
                errors.append(f"history[{index}] is not an object")
                continue
            raw = record.get("dispute_date")
            parsed = None
            if isinstance(raw, str):
                raw = raw.strip()
                for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        parsed = datetime.strptime(raw[:19], fmt).date()
                        break
                    except ValueError:
                        pass
            if parsed is None:
                errors.append(f"history[{index}].dispute_date is unreadable")
            elif today - timedelta(days=365) <= parsed <= today:
                history_count += 1

    limit = TIER_LIMITS.get(account_card)
    if account_card and limit is None:
        errors.append("card tier has no configured provisional-credit limit")

    eligible_reason = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
    goods_old_enough = reason != "goods_services_not_received" or (purchase is not None and today is not None and purchase < today - timedelta(days=30))
    account_old_enough = opened is not None and today is not None and opened <= today - timedelta(days=60)
    amount_ok = amount is not None and limit is not None and 25.0 <= amount <= limit
    merchant_ok = reason == "unauthorized_fraudulent_charge" or contacted is True
    history_ok = isinstance(history, list) and history_count <= 2
    eligibility = bool(eligible_reason and goods_old_enough and account_old_enough and amount_ok and merchant_ok and history_ok)

    arguments = {
        "transaction_id": transaction_id, "card_action": action,
        "card_last_4_digits": last4, "full_name": full_name, "user_id": user_id,
        "phone": phone, "email": email, "address": address,
        "contacted_merchant": contacted, "purchase_date": transaction.get("purchase_date"),
        "issue_noticed_date": data.get("issue_noticed_date"), "dispute_reason": reason,
        "resolution_requested": resolution, "eligible_for_provisional_credit": eligibility,
    }
    if resolution == "partial_refund" and not errors:
        arguments["partial_refund_amount"] = partial
    result = {
        "ready": not errors,
        "errors": errors,
        "eligibility": {
            "eligible_for_provisional_credit": eligibility,
            "account_at_least_60_days": account_old_enough,
            "eligible_reason": eligible_reason,
            "goods_not_received_more_than_30_days": goods_old_enough,
            "amount_within_tier_limit": amount_ok,
            "disputes_in_prior_12_months": history_count,
            "history_requirement_met": history_ok,
            "merchant_requirement_met": merchant_ok,
            "tier_limit": limit,
        },
    }
    if not errors:
        result["arguments"] = arguments
    return result


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(supplied), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ready": False, "errors": [str(exc)]}, separators=(",", ":")))
