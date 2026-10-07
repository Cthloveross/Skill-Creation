#!/usr/bin/env python3
"""Evaluate referral eligibility and choose a supported business-checking referral.

Reads the JSON schema documented in SKILL.md from stdin and emits JSON. This script
is advisory only and never calls banking tools or changes customer records.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

PRODUCTS = (
    {"account": "World Blue", "bonus": 300, "deposit": 25000, "window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"account": "True Blue", "bonus": 350, "deposit": 50000, "window_days": 120, "tenure_days": 90, "annual_cap": 15},
    {"account": "Beige", "bonus": 500, "deposit": 100000, "window_days": 120, "tenure_days": 120, "annual_cap": 15},
    {"account": "Lime Green", "bonus": 200, "deposit": 15000, "window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"account": "Hunter Green", "bonus": 175, "deposit": 10000, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"account": "Navy Blue", "bonus": 100, "deposit": 5000, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
)


def parse_datetime(value):
    """Return (datetime, is_date_only), normalizing naive values to UTC."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing date")
    raw = value.strip()
    date_only = "T" not in raw and " " not in raw
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, date_only


def normalized_account(value):
    return str(value or "").strip().lower().replace(" account", "")


def completed(record):
    return str(record.get("referral_status", "")).upper() == "COMPLETE"


def issue(code, message):
    return {"code": code, "message": message}


def main(data):
    missing = []
    blockers = []
    try:
        now, _ = parse_datetime(data.get("now"))
    except ValueError:
        return {"status": "needs_information", "issues": [issue("current_time_required", "A current timestamp is required to evaluate time-based limits.")]}

    referrer = data.get("referrer") if isinstance(data.get("referrer"), dict) else {}
    business = data.get("referred_business") if isinstance(data.get("referred_business"), dict) else {}
    deposit = data.get("deposit") if isinstance(data.get("deposit"), dict) else {}
    referrals = data.get("referrals") if isinstance(data.get("referrals"), list) else []

    if referrer.get("identity_verified") is not True:
        missing.append(issue("identity_verification_required", "Verify identity before using account-specific eligibility information."))
    if referrer.get("customer_record_resolved") is False:
        blockers.append(issue("customer_record_unresolved", "The referrer record could not be resolved."))

    opened = None
    try:
        opened, _ = parse_datetime(referrer.get("first_checking_opened"))
    except ValueError:
        missing.append(issue("first_checking_opened_required", "The opening date of the earliest checking account is required."))

    business_checks = (
        ("new_customer_no_account_in_last_12_months", "new_customer_required", "Confirm the referred business is new and has had no Rho-Bank checking, savings, or closed account in the past 12 months."),
        ("different_registered_address", "different_address_required", "Confirm the businesses are registered at different addresses."),
        ("different_primary_owner_from_existing_business_accounts", "different_primary_owner_required", "Confirm the primary authorized signer differs from every existing Rho-Bank business account."),
    )
    for field, code, message in business_checks:
        value = business.get(field)
        if value is None:
            missing.append(issue(code, message))
        elif value is not True:
            blockers.append(issue(code, message))

    amount = deposit.get("amount")
    if not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount < 0:
        missing.append(issue("deposit_amount_required", "Provide a non-negative anticipated qualifying-deposit amount."))
        amount = None
    if deposit.get("is_new_money") is None:
        missing.append(issue("new_money_required", "Confirm that the qualifying deposit is new money and not a Rho-Bank transfer."))
    elif deposit.get("is_new_money") is not True:
        blockers.append(issue("new_money_required", "A transfer from another Rho-Bank account cannot qualify as new money."))

    completed_records = []
    uncertain_rolling = False
    cutoff = now - timedelta(days=9)
    for record in referrals:
        if not isinstance(record, dict) or not completed(record):
            continue
        try:
            when, date_only = parse_datetime(record.get("date"))
        except ValueError:
            missing.append(issue("referral_timestamp_invalid", "A completed referral has no usable timestamp."))
            continue
        # A date-only value on/after the cutoff date might be either side of the exact cutoff.
        if date_only and cutoff.date() <= when.date() <= now.date():
            uncertain_rolling = True
        completed_records.append((when, record))

    if uncertain_rolling:
        missing.append(issue("exact_recent_referral_times_required", "Exact timestamps are required for completed referrals near the rolling nine-day boundary."))
    rolling_count = sum(1 for when, _ in completed_records if cutoff <= when <= now)
    if rolling_count >= 2:
        blockers.append(issue("rolling_nine_day_cap", "Two completed referral bonuses already fall within the rolling nine-day window."))

    if missing:
        return {"status": "needs_information", "issues": missing, "blocking_issues": blockers, "rolling_completed_count": rolling_count}
    if blockers:
        return {"status": "ineligible", "issues": blockers, "rolling_completed_count": rolling_count}

    tenure_days = (now - opened).total_seconds() / 86400
    eligible = []
    excluded = []
    for product in PRODUCTS:
        reasons = []
        if tenure_days < product["tenure_days"]:
            reasons.append("tenure_below_requirement")
        if amount < product["deposit"]:
            reasons.append("deposit_below_requirement")
        annual_count = sum(
            1 for when, record in completed_records
            if when.year == now.year and normalized_account(record.get("referred_account_type")) == normalized_account(product["account"])
        )
        if annual_count >= product["annual_cap"]:
            reasons.append("annual_cap_reached")
        entry = dict(product)
        entry["annual_completed_count"] = annual_count
        if reasons:
            entry["exclusion_reasons"] = reasons
            excluded.append(entry)
        else:
            eligible.append(entry)

    if not eligible:
        return {
            "status": "ineligible",
            "issues": [issue("no_supported_qualifying_product", "No supported referral product meets the verified tenure, deposit, and annual-cap conditions.")],
            "rolling_completed_count": rolling_count,
            "excluded_products": excluded,
        }

    recommendation = max(eligible, key=lambda item: item["bonus"])
    return {
        "status": "eligible",
        "rolling_completed_count": rolling_count,
        "recommendation": recommendation,
        "eligible_products": sorted(eligible, key=lambda item: item["bonus"], reverse=True),
        "general_conditions": [
            "The referred business must open the recommended account.",
            "The qualifying deposit must be new money within the stated window.",
            "The qualifying deposit must remain for at least 30 days after the qualifying period ends.",
            "Both accounts must remain in good standing; early closure may cause a clawback.",
            "Only one referral code and no other new-account promotion may be applied.",
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "needs_information", "issues": [issue("invalid_input", str(exc))]}))
