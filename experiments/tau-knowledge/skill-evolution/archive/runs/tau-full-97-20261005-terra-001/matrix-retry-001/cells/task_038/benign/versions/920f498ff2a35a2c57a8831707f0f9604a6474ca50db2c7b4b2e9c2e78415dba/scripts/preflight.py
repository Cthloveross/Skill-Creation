#!/usr/bin/env python3
"""Validate dispute/replacement data from JSON stdin; emit a JSON preflight report."""
import datetime as dt
import json
import sys

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
REPLACEMENT_REASONS = {"fraud_suspected", "lost", "stolen", "damaged", "expired", "other"}

TIER_DATA = {
    "Bronze Rewards Card": ("entry", 2500, 15, 2),
    "Bronze Rewards": ("entry", 2500, 15, 2),
    "EcoCard": ("entry", 2500, 15, 2),
    "Business Bronze Rewards Card": ("entry", 2500, 15, 2),
    "Business Bronze": ("entry", 2500, 15, 2),
    "Crypto-Cash Back Card": ("entry", 2500, 15, 2),
    "Silver Rewards Card": ("mid", 5000, 10, 3),
    "Silver Rewards": ("mid", 5000, 10, 3),
    "Business Silver Rewards Card": ("mid", 5000, 10, 3),
    "Business Silver": ("mid", 5000, 10, 3),
    "Green Rewards Card": ("mid", 5000, 10, 3),
    "Green Rewards": ("mid", 5000, 10, 3),
    "Silver Zoom Card": ("mid", 5000, 10, 3),
    "Silver Zoom": ("mid", 5000, 10, 3),
    "Gold Rewards Card": ("premium", 10000, 0, 4),
    "Business Gold Rewards Card": ("premium", 10000, 0, 4),
    "Platinum Rewards Card": ("elite", 15000, 0, 4),
    "Business Platinum Rewards Card": ("elite", 15000, 0, 4),
    "Diamond Elite Card": ("invitation", 25000, 0, 4),
    "Diamond Elite": ("invitation", 25000, 0, 4),
}

def date(value, label, errors):
    try:
        return dt.datetime.strptime(value, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        errors.append(f"{label} must be MM/DD/YYYY.")
        return None

def required(mapping, keys, prefix, errors):
    for key in keys:
        if mapping.get(key) in (None, ""):
            errors.append(f"{prefix}.{key} is required.")

def main(data):
    errors = []
    account = data.get("account") or {}
    customer = data.get("customer") or {}
    replacement = data.get("replacement") or {"requested": False}
    required(account, ["account_id", "card_type", "opened_date", "card_last_4_digits"], "account", errors)
    required(customer, ["full_name", "user_id", "phone", "email", "address"], "customer", errors)
    now = date(data.get("now_date"), "now_date", errors)
    opened = date(account.get("opened_date"), "account.opened_date", errors)
    last4 = str(account.get("card_last_4_digits", ""))
    if not (last4.isdigit() and len(last4) == 4):
        errors.append("account.card_last_4_digits must contain exactly four digits.")
    tier_info = TIER_DATA.get(account.get("card_type"))
    if not tier_info:
        errors.append("account.card_type is unsupported; tier and limits cannot be determined.")
        tier_info = (None, None, None, None)
    tier, limit, fee, replacement_limit = tier_info
    action = data.get("card_action")
    if action not in {"keep_active", "cancel_and_reissue"}:
        errors.append("card_action must be keep_active or cancel_and_reissue.")
    prior = data.get("prior_disputes_12_months")
    if not isinstance(prior, int) or prior < 0:
        errors.append("prior_disputes_12_months must be a nonnegative integer.")
        prior = 999999

    decisions, payloads = [], []
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        errors.append("At least one dispute is required.")
        disputes = []
    for i, d in enumerate(disputes):
        prefix = f"disputes[{i}]"
        required(d, ["transaction_id", "amount", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested"], prefix, errors)
        purchase = date(d.get("purchase_date"), prefix + ".purchase_date", errors)
        date(d.get("issue_noticed_date"), prefix + ".issue_noticed_date", errors)
        if d.get("dispute_reason") not in REASONS:
            errors.append(prefix + ".dispute_reason is not permitted.")
        if d.get("resolution_requested") not in RESOLUTIONS:
            errors.append(prefix + ".resolution_requested is not permitted.")
        if not isinstance(d.get("contacted_merchant"), bool):
            errors.append(prefix + ".contacted_merchant must be boolean.")
        try:
            amount = float(d.get("amount"))
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(prefix + ".amount must be a positive number.")
            amount = -1
        partial = d.get("partial_refund_amount")
        if d.get("resolution_requested") == "partial_refund":
            if not isinstance(partial, (int, float)) or partial <= 0 or partial > amount:
                errors.append(prefix + ".partial_refund_amount must be positive and no more than the transaction amount.")
        elif partial is not None:
            errors.append(prefix + ".partial_refund_amount is allowed only for partial_refund.")

        reasons = []
        eligible = True
        if not now or not opened or (now - opened).days < 60:
            eligible = False
            reasons.append("account has not been open at least 60 days")
        reason = d.get("dispute_reason")
        if reason not in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}:
            eligible = False
            reasons.append("dispute reason is not eligible")
        if reason == "goods_services_not_received" and (not purchase or not now or (now - purchase).days <= 30):
            eligible = False
            reasons.append("goods/services-not-received purchase is not more than 30 days old")
        if amount < 25 or limit is None or amount > limit:
            eligible = False
            reasons.append("amount is outside the provisional-credit tier limit")
        if prior > 2:
            eligible = False
            reasons.append("more than two prior disputes in the last 12 months")
        if reason != "unauthorized_fraudulent_charge" and d.get("contacted_merchant") is not True:
            eligible = False
            reasons.append("merchant was not contacted for a non-fraud dispute")
        decisions.append({"transaction_id": d.get("transaction_id"), "eligible_for_provisional_credit": eligible, "reasons": reasons})
        payload = {
            "transaction_id": d.get("transaction_id"), "card_action": action,
            "card_last_4_digits": last4, "full_name": customer.get("full_name"),
            "user_id": customer.get("user_id"), "phone": customer.get("phone"),
            "email": customer.get("email"), "address": customer.get("address"),
            "contacted_merchant": d.get("contacted_merchant"), "purchase_date": d.get("purchase_date"),
            "issue_noticed_date": d.get("issue_noticed_date"), "dispute_reason": reason,
            "resolution_requested": d.get("resolution_requested"),
            "eligible_for_provisional_credit": eligible,
        }
        if d.get("resolution_requested") == "partial_refund":
            payload["partial_refund_amount"] = partial
        payloads.append(payload)

    replacement_report = {"requested": bool(replacement.get("requested")), "eligible": None, "fee": fee, "payload": None}
    if replacement.get("requested"):
        required(replacement, ["reason", "shipping_address", "shipping_speed"], "replacement", errors)
        if replacement.get("reason") not in REPLACEMENT_REASONS:
            errors.append("replacement.reason is not permitted.")
        if replacement.get("shipping_speed") not in {"standard", "expedited"}:
            errors.append("replacement.shipping_speed must be standard or expedited.")
        pending = account.get("no_pending_replacement")
        count = account.get("replacement_count_60_days")
        if not isinstance(pending, bool):
            errors.append("account.no_pending_replacement must be a boolean verified from the pending-order check.")
        if not isinstance(count, int) or count < 0:
            errors.append("account.replacement_count_60_days must be a verified nonnegative integer.")
        if replacement.get("shipping_speed") == "expedited" and fee and replacement.get("fee_consent") is not True:
            errors.append("Explicit consent is required for the expedited-shipping fee.")
        eligible = pending is True and isinstance(count, int) and replacement_limit is not None and count < replacement_limit
        replacement_report["eligible"] = eligible
        if not eligible and not any(x.startswith("account.no_pending") or x.startswith("account.replacement_count") for x in errors):
            errors.append("Replacement is ineligible due to a pending order or the 60-day tier limit.")
        replacement_report["payload"] = {
            "account_id": account.get("account_id"), "reason": replacement.get("reason"),
            "shipping_address": replacement.get("shipping_address"), "shipping_speed": replacement.get("shipping_speed"),
            "expedited_fee_acknowledgement": bool(replacement.get("shipping_speed") == "expedited" and fee and replacement.get("fee_consent")),
            "notes": replacement.get("notes", "")
        }
    return {
        "valid": not errors, "errors": errors, "card_tier": tier,
        "provisional_credit_limit": limit, "expedited_fee": fee,
        "provisional_credit": decisions,
        "dispute_payloads": payloads if not errors else [],
        "replacement": replacement_report,
    }

if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"valid": False, "errors": ["Invalid input: " + str(exc)]}))
