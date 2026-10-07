#!/usr/bin/env python3
"""Validate dispute intake data and build filing payloads.

Reads one JSON object from stdin and writes one JSON object to stdout.  It does
not call banking tools or retain customer data.
"""
import json
import re
import sys
from datetime import datetime, timedelta
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
REQUIRED_PROFILE = ("full_name", "user_id", "phone", "email", "address")


def date_mmddyyyy(value):
    if not isinstance(value, str):
        raise ValueError("must be a MM/DD/YYYY string")
    return datetime.strptime(value, "%m/%d/%Y").date()


def history_date(value):
    """Accept common history dates while keeping filing dates strictly formatted."""
    if not isinstance(value, str):
        raise ValueError("must be a date string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError("unrecognized date")


def amount(value):
    if isinstance(value, bool):
        raise ValueError("must be numeric")
    try:
        text = str(value).replace("$", "").replace(",", "").strip()
        result = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError("must be numeric")
    if not result.is_finite():
        raise ValueError("must be finite")
    return result


def error(errors, prefix, message):
    errors.append(f"{prefix}: {message}")


def prior_count(data, today, errors):
    if "prior_dispute_count_12_months" in data:
        value = data["prior_dispute_count_12_months"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            error(errors, "prior_dispute_count_12_months", "must be a nonnegative integer")
            return None
        return value
    if "prior_disputes" not in data or not isinstance(data["prior_disputes"], list):
        error(errors, "history", "supply prior_dispute_count_12_months from the history lookup or prior_disputes")
        return None
    cutoff = today - timedelta(days=365)
    count = 0
    for index, record in enumerate(data["prior_disputes"]):
        try:
            when = history_date(record.get("dispute_date"))
        except (AttributeError, ValueError):
            error(errors, f"prior_disputes[{index}].dispute_date", "is required and must be parseable")
            continue
        if cutoff <= when <= today:
            count += 1
    return count


def main(data):
    errors = []
    profile = data.get("profile")
    if not isinstance(profile, dict):
        error(errors, "profile", "must be an object")
        profile = {}
    for field in REQUIRED_PROFILE:
        if not isinstance(profile.get(field), str) or not profile[field].strip():
            error(errors, f"profile.{field}", "is required")

    try:
        today = date_mmddyyyy(data.get("current_date"))
    except ValueError as exc:
        error(errors, "current_date", str(exc))
        today = None

    accounts = data.get("accounts")
    account_map = {}
    if not isinstance(accounts, list) or not accounts:
        error(errors, "accounts", "must be a nonempty list")
        accounts = []
    for index, account in enumerate(accounts):
        prefix = f"accounts[{index}]"
        if not isinstance(account, dict):
            error(errors, prefix, "must be an object")
            continue
        account_id = account.get("account_id")
        if not isinstance(account_id, str) or not account_id:
            error(errors, prefix + ".account_id", "is required")
            continue
        if account_id in account_map:
            error(errors, prefix + ".account_id", "must be unique")
            continue
        card_type = account.get("card_type")
        if card_type not in TIER_LIMITS:
            error(errors, prefix + ".card_type", "is unsupported for provisional-credit tiering")
        try:
            opened = date_mmddyyyy(account.get("date_of_account_open"))
        except ValueError as exc:
            error(errors, prefix + ".date_of_account_open", str(exc))
            opened = None
        last4 = account.get("card_last_4_digits")
        if not isinstance(last4, str) or not re.fullmatch(r"\d{4}", last4):
            error(errors, prefix + ".card_last_4_digits", "must be exactly four digits")
        account_map[account_id] = {"card_type": card_type, "opened": opened, "last4": last4}

    count = prior_count(data, today, errors) if today else None
    disputes = data.get("disputes")
    if not isinstance(disputes, list) or not disputes:
        error(errors, "disputes", "must be a nonempty list")
        disputes = []

    reports = []
    payloads = []
    seen_transactions = set()
    for index, dispute in enumerate(disputes):
        prefix = f"disputes[{index}]"
        local = []
        if not isinstance(dispute, dict):
            error(errors, prefix, "must be an object")
            continue
        txn = dispute.get("transaction_id")
        if not isinstance(txn, str) or not txn:
            local.append("transaction_id is required")
        elif txn in seen_transactions:
            local.append("transaction_id may appear only once")
        else:
            seen_transactions.add(txn)
        account_id = dispute.get("account_id")
        account = account_map.get(account_id)
        if account is None:
            local.append("account_id must reference a supplied account")
        reason = dispute.get("dispute_reason")
        if reason not in REASONS:
            local.append("dispute_reason is invalid")
        resolution = dispute.get("resolution_requested")
        if resolution not in RESOLUTIONS:
            local.append("resolution_requested is invalid")
        action = dispute.get("card_action")
        if action not in ACTIONS:
            local.append("card_action is invalid")
        contacted = dispute.get("contacted_merchant")
        if not isinstance(contacted, bool):
            local.append("contacted_merchant must be boolean")
        try:
            purchase = date_mmddyyyy(dispute.get("purchase_date"))
        except ValueError:
            local.append("purchase_date must be MM/DD/YYYY")
            purchase = None
        try:
            noticed = date_mmddyyyy(dispute.get("issue_noticed_date"))
        except ValueError:
            local.append("issue_noticed_date must be MM/DD/YYYY")
            noticed = None
        try:
            txn_amount = amount(dispute.get("transaction_amount"))
            if txn_amount <= 0:
                local.append("transaction_amount must be positive")
        except ValueError:
            local.append("transaction_amount must be numeric")
            txn_amount = None
        partial = None
        if resolution == "partial_refund":
            try:
                partial = amount(dispute.get("partial_refund_amount"))
                if partial <= 0:
                    local.append("partial_refund_amount must be positive")
                elif txn_amount is not None and partial > txn_amount:
                    local.append("partial_refund_amount cannot exceed transaction_amount")
            except ValueError:
                local.append("partial_refund_amount is required and must be numeric for partial_refund")

        for message in local:
            error(errors, prefix, message)
        eligibility_failures = []
        criteria = {}
        if not local and today and count is not None and account and txn_amount is not None and purchase:
            account_age_ok = account["opened"] is not None and (today - account["opened"]).days >= 60
            criteria["account_open_at_least_60_days"] = account_age_ok
            if not account_age_ok:
                eligibility_failures.append("account has not been open at least 60 days")
            reason_ok = reason in {"unauthorized_fraudulent_charge", "duplicate_charge"}
            if reason == "goods_services_not_received":
                reason_ok = (today - purchase).days > 30
            criteria["eligible_reason_and_delivery_age"] = reason_ok
            if not reason_ok:
                eligibility_failures.append("reason is not eligible, or goods/services-not-received purchase is not more than 30 days old")
            limit = TIER_LIMITS.get(account["card_type"])
            amount_ok = limit is not None and txn_amount >= Decimal("25") and txn_amount <= limit
            criteria["amount_within_tier_limit"] = amount_ok
            if not amount_ok:
                eligibility_failures.append("amount is under $25 or exceeds the card tier maximum")
            history_ok = count <= 2
            criteria["no_more_than_two_prior_disputes"] = history_ok
            if not history_ok:
                eligibility_failures.append("customer has more than two disputes in the prior 12 months")
            merchant_ok = reason == "unauthorized_fraudulent_charge" or contacted is True
            criteria["merchant_contact_requirement"] = merchant_ok
            if not merchant_ok:
                eligibility_failures.append("merchant was not contacted for a non-fraud dispute")
            eligible = not eligibility_failures
        else:
            eligible = None
            eligibility_failures.append("cannot determine until all required validated data and dispute history are available")

        reports.append({
            "transaction_id": txn,
            "eligible_for_provisional_credit": eligible,
            "criteria": criteria,
            "ineligibility_or_blocking_reasons": eligibility_failures,
        })
        if not local and account and today and count is not None and eligible is not None:
            payload = {
                "transaction_id": txn,
                "card_action": action,
                "card_last_4_digits": account["last4"],
                "full_name": profile.get("full_name"),
                "user_id": profile.get("user_id"),
                "phone": profile.get("phone"),
                "email": profile.get("email"),
                "address": profile.get("address"),
                "contacted_merchant": contacted,
                "purchase_date": dispute["purchase_date"],
                "issue_noticed_date": dispute["issue_noticed_date"],
                "dispute_reason": reason,
                "resolution_requested": resolution,
                "eligible_for_provisional_credit": eligible,
            }
            if resolution == "partial_refund":
                payload["partial_refund_amount"] = float(partial)
            payloads.append(payload)

    # Never return executable payloads when any global or per-record validation failed.
    ok = not errors
    if not ok:
        payloads = []
    return {
        "ok": ok,
        "validation_errors": errors,
        "prior_dispute_count_12_months": count,
        "dispute_assessments": reports,
        "payloads": payloads,
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("top-level input must be a JSON object")
        result = main(incoming)
    except Exception as exc:
        result = {"ok": False, "validation_errors": [f"input: {exc}"], "payloads": []}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
