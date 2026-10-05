#!/usr/bin/env python3
"""Prepare validated per-transaction credit-card dispute payloads.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
performs no bank action. See SKILL.md for the public input and output schema.
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
    for candidate in (value, value[:10]):
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                pass
    raise ValueError("must use MM/DD/YYYY or ISO date")


def normal_date(value, field):
    try:
        result = parse_date(value)
    except ValueError as exc:
        raise ValueError(f"{field} {exc}")
    return result.strftime("%m/%d/%Y"), result


def decimal_amount(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount


def one_year_ago(today):
    try:
        return today.replace(year=today.year - 1)
    except ValueError:  # Leap day.
        return today.replace(year=today.year - 1, day=28)


def prior_count(history, today, errors):
    if not isinstance(history, list):
        errors.append({"transaction_id": None, "error": "prior_disputes must be a successfully retrieved list"})
        return None
    dates = []
    for entry in history:
        if not isinstance(entry, dict) or "dispute_date" not in entry:
            errors.append({"transaction_id": None, "error": "each prior dispute needs dispute_date"})
            continue
        try:
            dates.append(parse_date(entry["dispute_date"]))
        except ValueError:
            errors.append({"transaction_id": None, "error": "a prior dispute has an invalid dispute_date"})
    if errors:
        return None
    start = one_year_ago(today)
    return sum(start <= item <= today for item in dates)


def add(errors, claim, message):
    errors.append({"transaction_id": claim.get("transaction_id"), "error": message})


def main(data):
    if not isinstance(data, dict):
        return {"ok": False, "errors": [{"transaction_id": None, "error": "input must be a JSON object"}], "submissions": []}
    try:
        _, today = normal_date(data.get("current_date"), "current_date")
    except ValueError as exc:
        return {"ok": False, "errors": [{"transaction_id": None, "error": str(exc)}], "submissions": []}

    errors = []
    profile = data.get("profile")
    if not isinstance(profile, dict):
        errors.append({"transaction_id": None, "error": "profile is required"})
        profile = {}
    for field in ("full_name", "user_id", "phone", "email", "address"):
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            errors.append({"transaction_id": None, "error": f"profile.{field} is required"})

    raw_accounts = data.get("accounts")
    if not isinstance(raw_accounts, list):
        errors.append({"transaction_id": None, "error": "accounts must be a list"})
        raw_accounts = []
    accounts = {item.get("account_id"): item for item in raw_accounts if isinstance(item, dict) and item.get("account_id")}
    count = prior_count(data.get("prior_disputes"), today, errors)

    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        errors.append({"transaction_id": None, "error": "claims must be a nonempty list"})
        claims = []
    seen_ids = set()
    for claim in claims:
        if isinstance(claim, dict) and isinstance(claim.get("transaction_id"), str) and claim["transaction_id"].strip():
            if claim["transaction_id"] in seen_ids:
                add(errors, claim, "transaction_id appears more than once")
            seen_ids.add(claim["transaction_id"])

    submissions = []
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append({"transaction_id": None, "error": "each claim must be an object"})
            continue
        local = []
        for field in ("transaction_id", "account_id", "purchase_date", "issue_noticed_date", "dispute_reason", "resolution_requested", "card_action"):
            if claim.get(field) in (None, ""):
                local.append(f"{field} is required")
        if not isinstance(claim.get("transaction_id"), str) or not claim.get("transaction_id", "").strip():
            local.append("transaction_id must be a nonempty string")
        if not isinstance(claim.get("contacted_merchant"), bool):
            local.append("contacted_merchant must be boolean")
        if claim.get("dispute_reason") not in REASONS:
            local.append("dispute_reason is not an allowed value")
        if claim.get("resolution_requested") not in RESOLUTIONS:
            local.append("resolution_requested is not an allowed value")
        if claim.get("card_action") not in ACTIONS:
            local.append("card_action is not an allowed value")

        account = accounts.get(claim.get("account_id"))
        if account is None:
            local.append("account_id was not found in accounts")
        try:
            purchase_text, purchase_day = normal_date(claim.get("purchase_date"), "purchase_date")
            if purchase_day > today:
                local.append("purchase_date cannot be after current_date")
        except ValueError as exc:
            local.append(str(exc)); purchase_text = None; purchase_day = None
        try:
            noticed_text, noticed_day = normal_date(claim.get("issue_noticed_date"), "issue_noticed_date")
            if noticed_day > today:
                local.append("issue_noticed_date cannot be after current_date")
        except ValueError as exc:
            local.append(str(exc)); noticed_text = None
        try:
            amount = decimal_amount(claim.get("transaction_amount"), "transaction_amount")
            if amount <= 0:
                local.append("transaction_amount must be positive")
        except ValueError as exc:
            local.append(str(exc)); amount = None

        partial_value = claim.get("partial_refund_amount")
        partial = None
        if claim.get("resolution_requested") == "partial_refund":
            try:
                partial = decimal_amount(partial_value, "partial_refund_amount")
                if partial <= 0:
                    local.append("partial_refund_amount must be positive")
            except ValueError as exc:
                local.append(str(exc))
        elif partial_value is not None:
            local.append("partial_refund_amount is allowed only for partial_refund")

        opened = None
        limit = None
        last4 = None
        if account is not None:
            last4 = account.get("last4")
            if not isinstance(last4, str) or len(last4) != 4 or not last4.isdigit():
                local.append("account last4 must be exactly four digits")
            try:
                opened = parse_date(account.get("opened_date"))
            except ValueError:
                local.append("account opened_date is invalid or missing")
            limit = TIER_LIMITS.get(account.get("card_type"))
            if limit is None:
                local.append("card type has no documented provisional-credit tier")

        if local:
            for message in local:
                add(errors, claim, message)
            continue

        disqualifiers = []
        reason = claim["dispute_reason"]
        if (today - opened).days < 60:
            disqualifiers.append("account has been open fewer than 60 days")
        if reason not in ELIGIBLE_REASONS:
            disqualifiers.append("dispute reason is not eligible")
        elif reason == "goods_services_not_received" and (today - purchase_day).days <= 30:
            disqualifiers.append("goods/services-not-received purchase is not more than 30 days old")
        if amount < Decimal("25"):
            disqualifiers.append("transaction amount is below $25")
        elif amount > limit:
            disqualifiers.append("transaction amount exceeds the card tier limit")
        if count is None:
            disqualifiers.append("prior-dispute history could not be evaluated")
        elif count > 2:
            disqualifiers.append("more than two prior disputes in the last 12 months")
        if reason != "unauthorized_fraudulent_charge" and not claim["contacted_merchant"]:
            disqualifiers.append("merchant was not contacted for a non-fraud dispute")

        tool_arguments = {
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
            "eligible_for_provisional_credit": not disqualifiers,
        }
        if partial is not None:
            tool_arguments["partial_refund_amount"] = float(partial)
        submissions.append({
            "transaction_id": claim["transaction_id"],
            "tool_arguments": tool_arguments,
            "provisional_credit": {
                "eligible": not disqualifiers,
                "reasons_not_eligible": disqualifiers,
                "tier_limit": float(limit),
                "prior_disputes_last_12_months": count,
            },
        })

    return {
        "ok": not errors,
        "errors": errors,
        "prior_disputes_last_12_months": count,
        "submissions": submissions,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [{"transaction_id": None, "error": str(exc)}], "submissions": []}, separators=(",", ":")))
