#!/usr/bin/env python3
"""Validate and prepare individual credit-card dispute filing payloads.

Reads one JSON object from stdin and writes one JSON object to stdout.  See
SKILL.md for the input schema.  This script performs no banking action.
"""
import json
import sys
from datetime import datetime, date
from decimal import Decimal, InvalidOperation

REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
    "goods_services_not_received", "goods_services_not_as_described",
    "canceled_subscription_still_charging", "refund_never_processed",
}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
ELIGIBLE_REASONS = {
    "unauthorized_fraudulent_charge", "duplicate_charge", "goods_services_not_received"
}
TIER_LIMITS = {
    "Bronze Rewards Card": Decimal("2500"),
    "EcoCard": Decimal("2500"),
    "Business Bronze Rewards Card": Decimal("2500"),
    "Crypto-Cash Back Card": Decimal("2500"),
    "Silver Rewards Card": Decimal("5000"),
    "Business Silver Rewards Card": Decimal("5000"),
    "Green Rewards Card": Decimal("5000"),
    "Silver Zoom Card": Decimal("5000"),
    "Gold Rewards Card": Decimal("10000"),
    "Business Gold Rewards Card": Decimal("10000"),
    "Platinum Rewards Card": Decimal("15000"),
    "Business Platinum Rewards Card": Decimal("15000"),
    "Diamond Elite Card": Decimal("25000"),
}

def parse_date(value):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    value = value.strip()
    # History tools may return a timestamp; its first ten characters are date-like.
    candidates = (value, value[:10])
    for candidate in candidates:
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError("must use MM/DD/YYYY or ISO date")

def date_mmddyyyy(value, field):
    try:
        parsed = parse_date(value)
    except ValueError as exc:
        raise ValueError(f"{field} {exc}")
    return parsed.strftime("%m/%d/%Y"), parsed

def money(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result

def in_last_12_months(dispute_day, today):
    # Calendar-year lookback, safely handling February 29.
    try:
        start = today.replace(year=today.year - 1)
    except ValueError:
        start = today.replace(year=today.year - 1, day=28)
    return start <= dispute_day <= today

def error(claim, message):
    return {"transaction_id": claim.get("transaction_id"), "error": message}

def main(data):
    top_errors = []
    try:
        _, today = date_mmddyyyy(data.get("current_date"), "current_date")
    except ValueError as exc:
        return {"ok": False, "errors": [{"transaction_id": None, "error": str(exc)}], "submissions": []}

    profile = data.get("profile")
    if not isinstance(profile, dict):
        return {"ok": False, "errors": [{"transaction_id": None, "error": "profile is required"}], "submissions": []}
    required_profile = ("full_name", "user_id", "phone", "email", "address")
    for field in required_profile:
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            top_errors.append({"transaction_id": None, "error": f"profile.{field} is required"})

    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        top_errors.append({"transaction_id": None, "error": "accounts must be a list"})
        accounts = []
    accounts_by_id = {a.get("account_id"): a for a in accounts if isinstance(a, dict) and a.get("account_id")}

    history = data.get("prior_disputes")
    prior_count = None
    if not isinstance(history, list):
        top_errors.append({"transaction_id": None, "error": "prior_disputes must be a successfully retrieved list"})
    else:
        dated_history = []
        for item in history:
            if not isinstance(item, dict) or "dispute_date" not in item:
                top_errors.append({"transaction_id": None, "error": "each prior dispute needs dispute_date"})
                continue
            try:
                dated_history.append(parse_date(item["dispute_date"]))
            except ValueError:
                top_errors.append({"transaction_id": None, "error": "a prior dispute has an invalid dispute_date"})
        if not top_errors:
            prior_count = sum(in_last_12_months(d, today) for d in dated_history)

    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        top_errors.append({"transaction_id": None, "error": "claims must be a nonempty list"})
        claims = []

    errors = list(top_errors)
    submissions = []
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append({"transaction_id": None, "error": "each claim must be an object"})
            continue
        local = []
        required = ("transaction_id", "account_id", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested", "card_action")
        for field in required:
            if claim.get(field) in (None, ""):
                local.append(f"{field} is required")
        if not isinstance(claim.get("contacted_merchant"), bool):
            local.append("contacted_merchant must be boolean")
        if claim.get("dispute_reason") not in REASONS:
            local.append("dispute_reason is not an allowed value")
        if claim.get("resolution_requested") not in RESOLUTIONS:
            local.append("resolution_requested is not an allowed value")
        if claim.get("card_action") not in ACTIONS:
            local.append("card_action is not an allowed value")
        account = accounts_by_id.get(claim.get("account_id"))
        if account is None:
            local.append("account_id was not found in accounts")
        try:
            purchase_text, purchase_day = date_mmddyyyy(claim.get("purchase_date"), "purchase_date")
            if purchase_day > today:
                local.append("purchase_date cannot be after current_date")
        except ValueError as exc:
            local.append(str(exc)); purchase_text = None; purchase_day = None
        try:
            noticed_text, noticed_day = date_mmddyyyy(claim.get("issue_noticed_date"), "issue_noticed_date")
            if noticed_day > today:
                local.append("issue_noticed_date cannot be after current_date")
        except ValueError as exc:
            local.append(str(exc)); noticed_text = None
        try:
            amount = money(claim.get("transaction_amount"), "transaction_amount")
            if amount <= 0:
                local.append("transaction_amount must be positive")
        except ValueError as exc:
            local.append(str(exc)); amount = None
        partial = claim.get("partial_refund_amount")
        if claim.get("resolution_requested") == "partial_refund":
            try:
                partial_amount = money(partial, "partial_refund_amount")
                if partial_amount <= 0:
                    local.append("partial_refund_amount must be positive")
            except ValueError as exc:
                local.append(str(exc)); partial_amount = None
        else:
            if partial is not None:
                local.append("partial_refund_amount is allowed only for partial_refund")
            partial_amount = None

        opened_day = None
        limit = None
        last4 = None
        if account is not None:
            last4 = account.get("last4")
            if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
                local.append("account last4 must be exactly four digits")
            try:
                opened_day = parse_date(account.get("opened_date"))
            except ValueError:
                local.append("account opened_date is invalid or missing")
            limit = TIER_LIMITS.get(account.get("card_type"))
            if limit is None:
                local.append("card type has no documented provisional-credit tier")
        if local:
            errors.extend(error(claim, message) for message in local)
            continue

        provisional_reasons = []
        reason = claim["dispute_reason"]
        if (today - opened_day).days < 60:
            provisional_reasons.append("account has been open fewer than 60 days")
        if reason not in ELIGIBLE_REASONS:
            provisional_reasons.append("dispute reason is not eligible")
        elif reason == "goods_services_not_received" and (today - purchase_day).days <= 30:
            provisional_reasons.append("goods/services-not-received purchase is not more than 30 days old")
        if amount < Decimal("25"):
            provisional_reasons.append("transaction amount is below $25")
        elif amount > limit:
            provisional_reasons.append("transaction amount exceeds the card tier limit")
        if prior_count is None:
            provisional_reasons.append("prior-dispute history could not be evaluated")
        elif prior_count > 2:
            provisional_reasons.append("more than two prior disputes in the last 12 months")
        if reason != "unauthorized_fraudulent_charge" and not claim["contacted_merchant"]:
            provisional_reasons.append("merchant was not contacted for a non-fraud dispute")
        eligible = not provisional_reasons
        tool_args = {
            "transaction_id": claim["transaction_id"],
            "card_action": claim["card_action"],
            "card_last_4_digits": last4,
            "full_name": profile["full_name"],
            "user_id": profile["user_id"],
            "phone": profile["phone"],
            "email": profile["email"],
            "address": profile["address"],
            "contacted_merchant": claim["contacted_merchant"],
            "purchase_date": purchase_text,
            "issue_noticed_date": noticed_text,
            "dispute_reason": reason,
            "resolution_requested": claim["resolution_requested"],
            "eligible_for_provisional_credit": eligible,
        }
        if partial_amount is not None:
            tool_args["partial_refund_amount"] = float(partial_amount)
        submissions.append({
            "transaction_id": claim["transaction_id"],
            "tool_arguments": tool_args,
            "provisional_credit": {"eligible": eligible, "reasons_not_eligible": provisional_reasons,
                                   "tier_limit": float(limit), "prior_disputes_last_12_months": prior_count},
        })
    return {"ok": not errors, "errors": errors, "prior_disputes_last_12_months": prior_count, "submissions": submissions}

if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [{"transaction_id": None, "error": str(exc)}], "submissions": []}, separators=(",", ":")))
