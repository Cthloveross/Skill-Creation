#!/usr/bin/env python3
"""Build validated, tool-ready credit-card dispute payloads.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
TIERS = {
    "Bronze Rewards Card": ("entry", Decimal("2500")),
    "EcoCard": ("entry", Decimal("2500")),
    "Business Bronze Rewards Card": ("entry", Decimal("2500")),
    "Crypto-Cash Back Card": ("entry", Decimal("2500")),
    "Silver Rewards Card": ("mid", Decimal("5000")),
    "Business Silver Rewards Card": ("mid", Decimal("5000")),
    "Green Rewards Card": ("mid", Decimal("5000")),
    "Silver Zoom Card": ("mid", Decimal("5000")),
    "Gold Rewards Card": ("premium", Decimal("10000")),
    "Business Gold Rewards Card": ("premium", Decimal("10000")),
    "Platinum Rewards Card": ("elite", Decimal("15000")),
    "Business Platinum Rewards Card": ("elite", Decimal("15000")),
    "Diamond Elite Card": ("invitation", Decimal("25000")),
}


def date_value(value):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value.strip()[:19], fmt).date()
        except ValueError:
            continue
    raise ValueError("must be MM/DD/YYYY, YYYY-MM-DD, or ISO datetime")


def amount_value(value):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("must be numeric")
    if not value.is_finite():
        raise ValueError("must be finite")
    return value


def prior_disputes(history, today, errors):
    cutoff = today.replace(year=today.year - 1)
    count = 0
    for index, record in enumerate(history):
        try:
            raw = record.get("dispute_date") if isinstance(record, dict) else record
            filed = date_value(raw)
            if cutoff <= filed <= today:
                count += 1
        except (AttributeError, ValueError) as exc:
            errors.append("dispute_history[%d]: %s" % (index, exc))
    return count


def main(data):
    errors, warnings, payloads, eligibility = [], [], [], []
    customer = data.get("customer", {})
    card = data.get("card", {})
    for field in ("full_name", "user_id", "phone", "email", "address"):
        if not isinstance(customer.get(field), str) or not customer[field].strip():
            errors.append("customer.%s is required" % field)
    last4 = card.get("last4")
    if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
        errors.append("card.last4 must be exactly four digits")
    if data.get("card_action") not in ACTIONS:
        errors.append("card_action must be keep_active or cancel_and_reissue")
    try:
        today = date_value(data.get("current_date"))
        opened = date_value(card.get("date_opened"))
    except ValueError as exc:
        errors.append("date input: %s" % exc)
        today = opened = None
    tier = TIERS.get(card.get("card_type"))
    if tier is None:
        errors.append("card.card_type is not a documented provisional-credit tier")
    history = data.get("dispute_history", [])
    if not isinstance(history, list):
        errors.append("dispute_history must be a list")
        history = []
    previous = prior_disputes(history, today, errors) if today else None
    disputes = data.get("disputes", [])
    if not isinstance(disputes, list) or not disputes:
        errors.append("disputes must be a nonempty list")
        disputes = []

    for index, item in enumerate(disputes):
        prefix, local = "disputes[%d]" % index, []
        if not isinstance(item, dict):
            errors.append(prefix + " must be an object")
            continue
        transaction_id, reason = item.get("transaction_id"), item.get("reason")
        resolution, contacted = item.get("resolution_requested"), item.get("contacted_merchant")
        if not isinstance(transaction_id, str) or not transaction_id.strip(): local.append("transaction_id is required")
        if reason not in REASONS: local.append("reason is invalid")
        if resolution not in RESOLUTIONS: local.append("resolution_requested is invalid")
        if not isinstance(contacted, bool): local.append("contacted_merchant must be boolean")
        try:
            purchase, noticed = date_value(item.get("purchase_date")), date_value(item.get("issue_noticed_date"))
            if today and (purchase > today or noticed > today): local.append("dates cannot be future dates")
        except ValueError as exc:
            local.append("date %s" % exc); purchase = noticed = None
        try:
            amount = amount_value(item.get("amount"))
            if amount <= 0: local.append("amount must be greater than zero")
        except ValueError as exc:
            local.append("amount %s" % exc); amount = None
        partial = item.get("partial_refund_amount")
        if resolution == "partial_refund":
            try:
                partial = amount_value(partial)
                if partial <= 0 or (amount is not None and partial > amount):
                    local.append("partial_refund_amount must be positive and no greater than amount")
            except ValueError as exc:
                local.append("partial_refund_amount %s" % exc)
        elif partial is not None:
            local.append("partial_refund_amount only applies to partial_refund")
        if local:
            errors.extend(prefix + "." + problem for problem in local)
            continue
        criteria = {
            "account_open_at_least_60_days": bool(today and opened and (today-opened).days >= 60),
            "qualifying_reason": reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"},
            "goods_not_received_more_than_30_days": reason != "goods_services_not_received" or bool(today and purchase and (today-purchase).days > 30),
            "amount_in_range": bool(tier and amount >= 25 and amount <= tier[1]),
            "no_more_than_two_prior_disputes": previous is not None and previous <= 2,
            "merchant_contact_satisfied": reason == "unauthorized_fraudulent_charge" or contacted,
        }
        eligible = all(criteria.values())
        eligibility.append({"transaction_id": transaction_id, "eligible_for_provisional_credit": eligible,
                            "criteria": criteria, "prior_disputes_in_last_12_months": previous,
                            "card_tier": tier[0] if tier else None})
        payload = {"transaction_id": transaction_id, "card_action": data.get("card_action"),
                   "card_last_4_digits": last4, "full_name": customer.get("full_name"),
                   "user_id": customer.get("user_id"), "phone": customer.get("phone"),
                   "email": customer.get("email"), "address": customer.get("address"),
                   "contacted_merchant": contacted, "purchase_date": purchase.strftime("%m/%d/%Y"),
                   "issue_noticed_date": noticed.strftime("%m/%d/%Y"), "dispute_reason": reason,
                   "resolution_requested": resolution, "eligible_for_provisional_credit": eligible}
        if resolution == "partial_refund": payload["partial_refund_amount"] = float(partial)
        payloads.append(payload)
    if previous is not None and previous > 2:
        warnings.append("More than two prior disputes in 12 months: provisional credit is unavailable.")
    return {"ready_to_file": not errors and bool(payloads), "errors": errors, "warnings": warnings,
            "payloads": payloads if not errors else [], "eligibility": eligibility}


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict): raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(source), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ready_to_file": False, "errors": [str(exc)], "warnings": [], "payloads": [], "eligibility": []}))
