#!/usr/bin/env python3
"""Validate dispute submissions and deterministically calculate provisional credit.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs no
network, banking, or filesystem actions beyond reading stdin.
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
LIMITS = {
    "entry": 2500.0, "mid": 5000.0, "premium": 10000.0,
    "elite": 15000.0, "invitation": 25000.0,
}


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None


def tier_group(value):
    text = str(value or "").lower()
    if any(x in text for x in ("diamond elite", "invitation")):
        return "invitation"
    if any(x in text for x in ("platinum", "elite")):
        return "elite"
    if any(x in text for x in ("gold", "premium")):
        return "premium"
    if any(x in text for x in ("silver", "green rewards", "silver zoom", "mid")):
        return "mid"
    if any(x in text for x in ("bronze", "ecocard", "crypto-cash", "entry")):
        return "entry"
    return None


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def main(data):
    errors = []
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    card = data.get("card") if isinstance(data.get("card"), dict) else {}
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        errors.append("disputes must be a nonempty list")
        disputes = []

    current = parse_date(data.get("current_date"))
    if not current:
        errors.append("current_date must use MM/DD/YYYY")
    opened = parse_date(card.get("opened_date"))
    if not opened:
        errors.append("card.opened_date must use MM/DD/YYYY")
    group = tier_group(card.get("tier"))
    if not group:
        errors.append("card.tier is not a recognized provisional-credit tier")
    if not data.get("identity_verified"):
        errors.append("identity_verified must be true before submitting or ordering")

    for field in ("full_name", "user_id", "phone", "email", "address"):
        if not isinstance(customer.get(field), str) or not customer[field].strip():
            errors.append("customer.%s is required" % field)
    if not isinstance(card.get("last4"), str) or not re.fullmatch(r"\d{4}", card["last4"]):
        errors.append("card.last4 must be exactly four digits")
    action = data.get("card_action")
    if action not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")

    history = data.get("prior_disputes")
    history_known = isinstance(history, list)
    recent_count = None
    if not history_known:
        errors.append("prior_disputes must be a complete list from dispute history")
    elif current:
        parsed_history = []
        for i, record in enumerate(history):
            d = parse_date(record.get("dispute_date")) if isinstance(record, dict) else None
            if not d:
                errors.append("prior_disputes[%d].dispute_date must use MM/DD/YYYY" % i)
            else:
                parsed_history.append(d)
        if not any(e.startswith("prior_disputes[") for e in errors):
            recent_count = sum(d >= current - timedelta(days=365) and d <= current for d in parsed_history)

    results = []
    payloads = []
    for i, item in enumerate(disputes):
        item_errors = []
        if not isinstance(item, dict):
            results.append({"index": i, "eligible_for_provisional_credit": None,
                            "errors": ["dispute must be an object"], "criteria": {}})
            continue
        for field in ("transaction_id", "purchase_date", "issue_noticed_date"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                item_errors.append("%s is required" % field)
        purchase = parse_date(item.get("purchase_date"))
        noticed = parse_date(item.get("issue_noticed_date"))
        if item.get("purchase_date") and not purchase:
            item_errors.append("purchase_date must use MM/DD/YYYY")
        if item.get("issue_noticed_date") and not noticed:
            item_errors.append("issue_noticed_date must use MM/DD/YYYY")
        if purchase and noticed and noticed < purchase:
            item_errors.append("issue_noticed_date cannot precede purchase_date")
        amount = item.get("amount")
        if not number(amount) or amount <= 0:
            item_errors.append("amount must be a positive number")
        reason = item.get("dispute_reason")
        if reason not in REASONS:
            item_errors.append("dispute_reason is invalid")
        resolution = item.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            item_errors.append("resolution_requested is invalid")
        contacted = item.get("contacted_merchant")
        if not isinstance(contacted, bool):
            item_errors.append("contacted_merchant must be boolean")
        partial = item.get("partial_refund_amount")
        if resolution == "partial_refund":
            if not number(partial) or partial <= 0:
                item_errors.append("partial_refund_amount must be a positive number for partial_refund")
            elif number(amount) and partial > amount:
                item_errors.append("partial_refund_amount cannot exceed amount")
        elif partial is not None:
            item_errors.append("partial_refund_amount is allowed only for partial_refund")

        criteria = {}
        if current and opened:
            criteria["account_open_at_least_60_days"] = (current - opened).days >= 60
        else:
            criteria["account_open_at_least_60_days"] = None
        criteria["eligible_reason"] = reason in {
            "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
        } if reason in REASONS else None
        if reason == "goods_services_not_received":
            criteria["goods_not_received_purchase_more_than_30_days_ago"] = (
                (current - purchase).days > 30 if current and purchase else None
            )
        else:
            criteria["goods_not_received_purchase_more_than_30_days_ago"] = True
        criteria["amount_within_tier_limit"] = (
            25.0 <= float(amount) <= LIMITS[group] if number(amount) and group else None
        )
        criteria["no_more_than_two_prior_disputes_in_12_months"] = (
            recent_count <= 2 if recent_count is not None else None
        )
        criteria["merchant_contact_for_nonfraud"] = (
            True if reason == "unauthorized_fraudulent_charge" else
            contacted if isinstance(contacted, bool) and reason in REASONS else None
        )
        values = list(criteria.values())
        eligible = False if any(v is False for v in values) else (True if all(v is True for v in values) else None)
        if eligible is None:
            item_errors.append("provisional-credit eligibility cannot be determined from supplied data")

        result = {"index": i, "transaction_id": item.get("transaction_id"),
                  "eligible_for_provisional_credit": eligible,
                  "criteria": criteria, "errors": item_errors}
        results.append(result)
        if not item_errors and not errors:
            payload = {
                "transaction_id": item["transaction_id"],
                "card_action": action,
                "card_last_4_digits": card["last4"],
                "full_name": customer["full_name"],
                "user_id": customer["user_id"],
                "phone": customer["phone"],
                "email": customer["email"],
                "address": customer["address"],
                "contacted_merchant": contacted,
                "purchase_date": item["purchase_date"],
                "issue_noticed_date": item["issue_noticed_date"],
                "dispute_reason": reason,
                "resolution_requested": resolution,
                "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund":
                payload["partial_refund_amount"] = partial
            payloads.append(payload)

    ready = not errors and len(payloads) == len(disputes) and all(not r["errors"] for r in results)
    return {
        "ready_to_submit": ready,
        "errors": errors,
        "recent_prior_dispute_count": recent_count,
        "provisional_credit": results,
        "dispute_payloads": payloads if ready else [],
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ready_to_submit": False, "errors": [str(exc)], "dispute_payloads": []}, separators=(",", ":")))
