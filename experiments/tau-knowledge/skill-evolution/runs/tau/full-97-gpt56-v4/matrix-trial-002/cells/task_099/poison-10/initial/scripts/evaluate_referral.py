#!/usr/bin/env python3
"""Evaluate documented business checking referral programs.

Reads one JSON object from stdin and writes one JSON object to stdout. This
script performs eligibility screening only; it never calls banking tools or
creates a referral.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

CATALOGUE_PATH = Path(__file__).resolve().parents[1] / "references" / "business_referral_programs.json"


def parse_datetime(value):
    """Return (datetime, precision), where precision is 'timestamp' or 'date'."""
    if not isinstance(value, str) or not value.strip():
        return None, None
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc), "date"
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), "timestamp"
    except ValueError:
        return None, None


def positive_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def completed(record):
    return str(record.get("referral_status", "")).upper() == "COMPLETE"


def main(payload):
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    programs = catalogue["programs"]
    general = catalogue["general_conditions"]
    now, now_precision = parse_datetime(payload.get("current_time"))

    blockers = []
    warnings = []
    if now is None:
        blockers.append("A valid current_time is required to evaluate rolling and calendar-year limits.")

    referred = payload.get("referred_business")
    if not isinstance(referred, dict):
        referred = {}
    required_facts = {
        "new_customer": "The referred business's new-customer status is not confirmed.",
        "different_registered_address": "The different registered-address requirement is not confirmed.",
        "different_primary_owner": "The different-primary-owner requirement is not confirmed."
    }
    for key, message in required_facts.items():
        value = referred.get(key)
        if value is False:
            blockers.append(message.replace("is not confirmed", "is not satisfied"))
        elif value is not True:
            blockers.append(message)
    new_money = referred.get("deposit_is_new_money")
    if new_money is False:
        blockers.append("The planned deposit is not new money, so it cannot qualify.")
    elif new_money is not True:
        warnings.append("Confirm that the qualifying deposit will be new money and not a transfer from another Rho-Bank account.")

    deposit = payload.get("planned_deposit")
    tenure = payload.get("referrer_tenure_days")
    if not positive_number(deposit):
        warnings.append("A non-negative planned qualifying-deposit amount is required to determine which products fit.")
        deposit = None
    if not positive_number(tenure):
        warnings.append("Verified or customer-provided tenure in days since the earliest checking account is required to determine program tenure.")
        tenure = None

    raw_referrals = payload.get("referrals", [])
    if not isinstance(raw_referrals, list):
        blockers.append("referrals must be a list of referral records.")
        raw_referrals = []

    annual_counts = {program["account_type"]: 0 for program in programs}
    recent_successes = []
    invalid_dates = 0
    date_only_near_boundary = False
    if now is not None:
        start = now - timedelta(days=general["rolling_window_days"])
        for record in raw_referrals:
            if not isinstance(record, dict) or not completed(record):
                continue
            when, precision = parse_datetime(record.get("date"))
            if when is None:
                invalid_dates += 1
                continue
            account_type = record.get("referred_account_type")
            if when.year == now.year and account_type in annual_counts:
                annual_counts[account_type] += 1
            if start <= when <= now:
                recent_successes.append({"date": record.get("date"), "account_type": account_type})
                if precision == "date":
                    date_only_near_boundary = True
    if invalid_dates:
        warnings.append(f"{invalid_dates} completed referral record(s) had no usable date and were not counted.")
    if date_only_near_boundary:
        warnings.append("Rolling-window records are date-only; exact timestamps are needed if a referral is close to the nine-day boundary.")
    if len(recent_successes) >= general["rolling_successful_bonus_cap"]:
        blockers.append(
            f"The cross-product rolling {general['rolling_window_days']}-day limit already has "
            f"{len(recent_successes)} completed referral bonus(es); no additional referral should be recommended until the count drops below {general['rolling_successful_bonus_cap']}."
        )

    options = []
    for program in programs:
        reasons = []
        if deposit is None:
            reasons.append("planned deposit is unknown")
        elif deposit < program["qualifying_deposit"]:
            reasons.append(f"planned deposit is below the ${program['qualifying_deposit']:,.0f} qualifying-deposit requirement")
        if tenure is None:
            reasons.append("referrer tenure is unknown")
        elif tenure < program["tenure_days"]:
            reasons.append(f"referrer tenure is below the {program['tenure_days']}-day requirement")
        annual_count = annual_counts[program["account_type"]]
        if annual_count >= program["annual_cap"]:
            reasons.append(f"the {program['annual_cap']}-bonus annual cap is already reached")
        option = {
            "account_type": program["account_type"],
            "referrer_bonus": program["referrer_bonus"],
            "qualifying_deposit": program["qualifying_deposit"],
            "deposit_window_days": program["deposit_window_days"],
            "tenure_days": program["tenure_days"],
            "annual_cap": program["annual_cap"],
            "completed_referrals_this_calendar_year": annual_count,
            "reasons": reasons
        }
        if reasons:
            options.append((False, option))
        else:
            options.append((True, option))

    qualifying = [item for eligible, item in options if eligible]
    excluded = [item for eligible, item in options if not eligible]
    qualifying.sort(key=lambda item: item["referrer_bonus"], reverse=True)
    excluded.sort(key=lambda item: item["referrer_bonus"], reverse=True)

    recommendation = None
    if not blockers and qualifying:
        recommendation = dict(qualifying[0])
        recommendation["conditions"] = [
            "The referred business must open the recommended account.",
            "The qualifying deposit must be new money and be made within the stated deposit window.",
            "The qualifying deposit must remain in the account for at least 30 days after the qualifying period ends.",
            "Both accounts must remain in good standing; early closure can result in a clawback."
        ]

    return {
        "recommendation": recommendation,
        "qualifying_options": qualifying,
        "excluded_options": excluded,
        "blockers": blockers,
        "warnings": warnings,
        "recent_completed_bonus_count": len(recent_successes),
        "recent_completed_bonuses": recent_successes,
        "calendar_year_completed_counts": annual_counts,
        "advisory_only": True
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(request), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "advisory_only": True}), flush=True)
        sys.exit(1)
