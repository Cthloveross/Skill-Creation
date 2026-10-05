#!/usr/bin/env python3
"""Validate dispute intakes and build file_credit_card_transaction_dispute_4829 arguments.
Reads the JSON schema documented in SKILL.md from stdin and writes JSON to stdout.
This program is pure validation/planning: it does not invoke banking tools.
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
LIMITS = {
    "Bronze Rewards Card": Decimal("2500"), "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"), "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"), "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"), "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"), "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"), "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}
REQUIRED_PROFILE = ("full_name", "user_id", "phone", "email", "address")

def date(value):
    if not isinstance(value, str):
        raise ValueError("must be a MM/DD/YYYY string")
    return datetime.strptime(value, "%m/%d/%Y").date()

def money(value):
    if isinstance(value, bool):
        raise InvalidOperation
    result = Decimal(str(value))
    if not result.is_finite():
        raise InvalidOperation
    return result

def main(data):
    global_errors = []
    try:
        today = date(data.get("as_of_date"))
    except (ValueError, TypeError):
        today = None
        global_errors.append("as_of_date must be MM/DD/YYYY")
    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    missing_profile = [k for k in REQUIRED_PROFILE if not isinstance(profile.get(k), str) or not profile[k].strip()]
    if missing_profile:
        global_errors.append("profile missing nonempty: " + ", ".join(missing_profile))
    count = data.get("prior_disputes_past_12_months")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        global_errors.append("prior_disputes_past_12_months must be a nonnegative integer")
        count = None

    cards_by_type = {}
    for card in data.get("cards", []) if isinstance(data.get("cards"), list) else []:
        if not isinstance(card, dict):
            continue
        typ = card.get("card_type")
        if isinstance(typ, str):
            cards_by_type.setdefault(typ, []).append(card)

    outputs = []
    disputes = data.get("disputes")
    if not isinstance(disputes, list):
        return {"ok": False, "global_errors": global_errors + ["disputes must be a list"], "submissions": []}
    for item in disputes:
        errors = list(global_errors)
        factors = []
        if not isinstance(item, dict):
            outputs.append({"can_submit": False, "errors": errors + ["dispute must be an object"]})
            continue
        required = ("transaction_id", "card_type", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested", "card_action")
        for key in required:
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(key + " must be a nonempty string")
        if not isinstance(item.get("contacted_merchant"), bool):
            errors.append("contacted_merchant must be boolean")
        reason = item.get("dispute_reason")
        resolution = item.get("resolution_requested")
        action = item.get("card_action")
        if reason not in REASONS: errors.append("unsupported dispute_reason")
        if resolution not in RESOLUTIONS: errors.append("unsupported resolution_requested")
        if action not in ACTIONS: errors.append("unsupported card_action")
        try:
            amount = money(item.get("transaction_amount"))
            if amount <= 0: errors.append("transaction_amount must be positive")
        except (InvalidOperation, ValueError, TypeError):
            amount = None; errors.append("transaction_amount must be a finite number")
        try:
            purchased = date(item.get("purchase_date"))
            noticed = date(item.get("issue_noticed_date"))
            if noticed < purchased: errors.append("issue_noticed_date cannot precede purchase_date")
            if today and (purchased > today or noticed > today): errors.append("purchase and noticed dates cannot be future dates")
        except (ValueError, TypeError):
            purchased = None; errors.append("purchase_date and issue_noticed_date must be MM/DD/YYYY")
        partial = item.get("partial_refund_amount")
        if resolution == "partial_refund":
            try:
                partial = money(partial)
                if partial <= 0 or (amount is not None and partial > amount):
                    errors.append("partial_refund_amount must be positive and no greater than transaction_amount")
            except (InvalidOperation, ValueError, TypeError):
                errors.append("partial_refund_amount is required and must be a finite number")
        elif partial is not None:
            errors.append("partial_refund_amount is allowed only for partial_refund")

        matches = cards_by_type.get(item.get("card_type"), [])
        if len(matches) != 1:
            errors.append("card_type must identify exactly one supplied card")
            card = None
        else:
            card = matches[0]
        if card is not None:
            last4 = card.get("card_last_4_digits")
            if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
                errors.append("card_last_4_digits must be exactly four digits")
            try:
                opened = date(card.get("account_open_date"))
                if today and opened > today: errors.append("account_open_date cannot be future")
            except (ValueError, TypeError):
                opened = None; errors.append("account_open_date must be MM/DD/YYYY")
        else:
            opened = None

        eligible = False
        if not errors and card is not None:
            age_ok = (today - opened).days >= 60
            reason_ok = reason in {"unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"}
            delivery_ok = reason != "goods_services_not_received" or (today - purchased).days > 30
            amount_ok = amount >= Decimal("25") and amount <= LIMITS.get(card["card_type"], Decimal("-1"))
            history_ok = count <= 2
            merchant_ok = reason == "unauthorized_fraudulent_charge" or item["contacted_merchant"]
            eligible = age_ok and reason_ok and delivery_ok and amount_ok and history_ok and merchant_ok
            factors = [
                {"account_open_at_least_60_days": age_ok}, {"eligible_reason": reason_ok},
                {"goods_not_received_over_30_days": delivery_ok}, {"amount_in_range": amount_ok},
                {"previous_disputes_at_most_2": history_ok}, {"merchant_contact_requirement_met": merchant_ok},
            ]
        out = {"transaction_id": item.get("transaction_id"), "can_submit": not errors, "errors": errors,
               "provisional_credit": {"eligible": eligible, "factors": factors}}
        if not errors:
            args = {
                "transaction_id": item["transaction_id"], "card_action": action,
                "card_last_4_digits": card["card_last_4_digits"], "full_name": profile["full_name"],
                "user_id": profile["user_id"], "phone": profile["phone"], "email": profile["email"],
                "address": profile["address"], "contacted_merchant": item["contacted_merchant"],
                "purchase_date": item["purchase_date"], "issue_noticed_date": item["issue_noticed_date"],
                "dispute_reason": reason, "resolution_requested": resolution,
                "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund": args["partial_refund_amount"] = float(partial)
            out["tool_arguments"] = args
        outputs.append(out)
    return {"ok": not global_errors and all(x["can_submit"] for x in outputs), "global_errors": global_errors, "submissions": outputs}

if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "global_errors": ["invalid input: " + str(exc)], "submissions": []}))
