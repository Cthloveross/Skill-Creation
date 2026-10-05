#!/usr/bin/env python3
"""Validate credit-card dispute intake and emit filing payloads.

Input: one JSON object on stdin, as documented in SKILL.md.
Output: one JSON object with ok, validation_errors, dispute_assessments, and
payloads. This program does not call banking tools.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

REASONS = {"unauthorized_fraudulent_charge", "duplicate_charge", "incorrect_amount",
           "goods_services_not_received", "goods_services_not_as_described",
           "canceled_subscription_still_charging", "refund_never_processed"}
RESOLUTIONS = {"full_refund", "partial_refund", "reversal_of_charge"}
ACTIONS = {"keep_active", "cancel_and_reissue"}
LIMITS = {
    "Bronze Rewards Card": 2500, "EcoCard": 2500, "Business Bronze Rewards Card": 2500,
    "Crypto-Cash Back Card": 2500, "Silver Rewards Card": 5000,
    "Business Silver Rewards Card": 5000, "Green Rewards Card": 5000,
    "Silver Zoom Card": 5000, "Gold Rewards Card": 10000,
    "Business Gold Rewards Card": 10000, "Platinum Rewards Card": 15000,
    "Business Platinum Rewards Card": 15000, "Diamond Elite Card": 25000,
}
PROFILE_FIELDS = ("full_name", "user_id", "phone", "email", "address")


def date(value, history=False):
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    formats = ("%m/%d/%Y", "%Y-%m-%d") if history else ("%m/%d/%Y",)
    for fmt in formats:
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError("must use MM/DD/YYYY" if not history else "is not parseable")


def money(value):
    if isinstance(value, bool):
        raise ValueError("must be numeric")
    try:
        result = Decimal(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError("must be numeric")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


def main(data):
    errors, payloads, assessments = [], [], []
    try:
        today = date(data.get("current_date"))
    except ValueError as exc:
        today = None
        errors.append("current_date: " + str(exc))

    profile = data.get("profile") if isinstance(data.get("profile"), dict) else {}
    if not profile:
        errors.append("profile: must be an object")
    for key in PROFILE_FIELDS:
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            errors.append("profile.%s: is required" % key)

    accounts, account_map = data.get("accounts"), {}
    if not isinstance(accounts, list) or not accounts:
        errors.append("accounts: must be a nonempty list")
        accounts = []
    for i, record in enumerate(accounts):
        p = "accounts[%d]" % i
        if not isinstance(record, dict):
            errors.append(p + ": must be an object")
            continue
        aid = record.get("account_id")
        if not isinstance(aid, str) or not aid or aid in account_map:
            errors.append(p + ".account_id: must be present and unique")
            continue
        try:
            opened = date(record.get("date_of_account_open"))
        except ValueError as exc:
            opened = None
            errors.append(p + ".date_of_account_open: " + str(exc))
        last4 = record.get("card_last_4_digits")
        if not isinstance(last4, str) or not re.fullmatch(r"\d{4}", last4):
            errors.append(p + ".card_last_4_digits: must be exactly four digits")
        tier = record.get("card_type")
        if tier not in LIMITS:
            errors.append(p + ".card_type: unsupported for tiering")
        account_map[aid] = {"opened": opened, "last4": last4, "tier": tier}

    count = data.get("prior_dispute_count_12_months")
    if count is None and isinstance(data.get("prior_disputes"), list) and today:
        count = 0
        for i, item in enumerate(data["prior_disputes"]):
            try:
                when = date(item.get("dispute_date"), history=True)
                count += int(today - timedelta(days=365) <= when <= today)
            except (AttributeError, ValueError):
                errors.append("prior_disputes[%d].dispute_date: is required and parseable" % i)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        errors.append("history: provide a nonnegative pre-batch dispute count or parseable prior_disputes")
        count = None

    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        errors.append("disputes: must be a nonempty list")
        disputes = []
    seen = set()
    for i, d in enumerate(disputes):
        p, local = "disputes[%d]" % i, []
        if not isinstance(d, dict):
            errors.append(p + ": must be an object")
            continue
        txn, aid = d.get("transaction_id"), d.get("account_id")
        if not isinstance(txn, str) or not txn or txn in seen:
            local.append("transaction_id must be present and unique")
        else:
            seen.add(txn)
        account = account_map.get(aid)
        if not account:
            local.append("account_id must reference an account")
        reason, resolution, action, contacted = (d.get("dispute_reason"), d.get("resolution_requested"),
                                                   d.get("card_action"), d.get("contacted_merchant"))
        if reason not in REASONS: local.append("dispute_reason is invalid")
        if resolution not in RESOLUTIONS: local.append("resolution_requested is invalid")
        if action not in ACTIONS: local.append("card_action is invalid")
        if not isinstance(contacted, bool): local.append("contacted_merchant must be boolean")
        try:
            purchase = date(d.get("purchase_date"))
            noticed = date(d.get("issue_noticed_date"))
        except ValueError:
            purchase = None
            local.append("purchase_date and issue_noticed_date must use MM/DD/YYYY")
        try:
            value = money(d.get("transaction_amount"))
            if value <= 0: local.append("transaction_amount must be positive")
        except ValueError:
            value = None; local.append("transaction_amount must be numeric")
        partial = None
        if resolution == "partial_refund":
            try:
                partial = money(d.get("partial_refund_amount"))
                if partial <= 0 or (value is not None and partial > value):
                    local.append("partial_refund_amount must be positive and no greater than transaction_amount")
            except ValueError:
                local.append("partial_refund_amount is required and numeric for partial_refund")
        elif "partial_refund_amount" in d:
            local.append("partial_refund_amount is allowed only for partial_refund")
        for item in local: errors.append(p + ": " + item)

        failures, criteria = [], {}
        if not local and account and today and count is not None and purchase and value is not None:
            criteria["account_open_at_least_60_days"] = (today - account["opened"]).days >= 60
            criteria["eligible_reason_and_delivery_age"] = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"} or (reason == "goods_services_not_received" and (today-purchase).days > 30)
            criteria["amount_within_tier_limit"] = Decimal("25") <= value <= Decimal(LIMITS[account["tier"]])
            criteria["no_more_than_two_prior_disputes"] = count <= 2
            criteria["merchant_contact_requirement"] = reason == "unauthorized_fraudulent_charge" or contacted
            failures = [k for k, passed in criteria.items() if not passed]
            eligible = not failures
        else:
            eligible = None; failures = ["cannot determine until required inputs validate"]
        assessments.append({"transaction_id": txn, "eligible_for_provisional_credit": eligible,
                            "criteria": criteria, "ineligibility_or_blocking_reasons": failures})
        if not local and account and eligible is not None:
            payload = {"transaction_id": txn, "card_action": action, "card_last_4_digits": account["last4"],
                       "full_name": profile.get("full_name"), "user_id": profile.get("user_id"),
                       "phone": profile.get("phone"), "email": profile.get("email"), "address": profile.get("address"),
                       "contacted_merchant": contacted, "purchase_date": d["purchase_date"],
                       "issue_noticed_date": d["issue_noticed_date"], "dispute_reason": reason,
                       "resolution_requested": resolution, "eligible_for_provisional_credit": eligible}
            if resolution == "partial_refund": payload["partial_refund_amount"] = float(partial)
            payloads.append(payload)
    ok = not errors
    return {"ok": ok, "validation_errors": errors, "prior_dispute_count_12_months": count,
            "dispute_assessments": assessments, "payloads": payloads if ok else []}

if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict): raise ValueError("top-level input must be an object")
        answer = main(raw)
    except Exception as exc:
        answer = {"ok": False, "validation_errors": ["input: %s" % exc], "payloads": []}
    print(json.dumps(answer, separators=(",", ":")))
