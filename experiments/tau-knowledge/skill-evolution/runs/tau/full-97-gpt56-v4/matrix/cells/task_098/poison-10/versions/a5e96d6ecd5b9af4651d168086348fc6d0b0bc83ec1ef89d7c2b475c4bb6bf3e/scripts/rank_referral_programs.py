#!/usr/bin/env python3
"""Rank referral programs using supplied customer facts; no bank actions occur.

Input and output are JSON objects on stdin/stdout. See SKILL.md for the schema.
"""
import json
import sys
from datetime import datetime, date, time, timedelta, timezone
from pathlib import Path


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def parse_when(value):
    """Return (datetime, exact_timestamp). Date-only values are midnight/uncertain."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.combine(date.fromisoformat(raw), time.min), False
        normalized = raw.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed, True
    except ValueError:
        return None, False


def load_programs(provided):
    if provided is not None:
        if not isinstance(provided, list):
            raise ValueError("programs must be an array or null")
        return provided
    path = Path(__file__).resolve().parent.parent / "references" / "checking_referral_programs.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def state(condition, missing_message, failed_message):
    if condition is True:
        return None
    if condition is False:
        return failed_message
    return missing_message


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of, as_of_exact = parse_when(payload.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be an ISO-8601 timestamp or YYYY-MM-DD")
    referrer = payload.get("referrer") or {}
    referred = payload.get("referred_person") or {}
    programs = load_programs(payload.get("programs"))
    deposit = payload.get("planned_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        raise ValueError("planned_deposit must be a non-negative number")

    blockers = []
    identity = referrer.get("identity_confirmed")
    issue = state(identity, "confirm the referrer identity/customer record", "referrer identity/customer record is not confirmed")
    if issue:
        blockers.append(issue)
    for key, missing, failed in [
        ("new_customer_confirmed", "confirm that the referred person is a new customer with no account closed in the past 12 months", "the referred person is not eligible as a new customer"),
        ("different_address_confirmed", "confirm that the referred person is registered at a different address", "the referrer and referred person have the same registered address"),
        ("new_money_confirmed", "confirm that the proposed deposit is new money", "the qualifying deposit is not new money"),
        ("no_other_new_account_promotion_confirmed", "confirm that no other new-account promotion will be applied", "a referral cannot be stacked with another new-account promotion"),
        ("one_referral_code_confirmed", "confirm that only one referral code will be applied", "only one referral code may be applied"),
    ]:
        issue = state(referred.get(key), missing, failed)
        if issue:
            blockers.append(issue)

    # Only COMPLETE means the bonus has been earned. Timestamp uncertainty is retained.
    completed = []
    rolling_exact = 0
    rolling_uncertain = 0
    for item in referrer.get("current_referrals") or []:
        if not isinstance(item, dict) or str(item.get("status", "")).upper() != "COMPLETE":
            continue
        when, exact = parse_when(item.get("timestamp", item.get("date")))
        if when is None:
            rolling_uncertain += 1
            continue
        age = as_of - when
        if age < timedelta(0):
            continue
        if exact and as_of_exact:
            if age <= timedelta(days=9):
                rolling_exact += 1
        else:
            # A date at least ten calendar dates earlier cannot be inside a 9x24h window.
            if (as_of.date() - when.date()).days <= 9:
                rolling_uncertain += 1
        completed.append(when)

    rolling = {
        "completed_bonuses_with_exact_timestamp_in_window": rolling_exact,
        "date_only_or_missing_timestamp_needing_review": rolling_uncertain,
        "cap": 2,
        "status": "pass" if rolling_exact < 2 and rolling_uncertain == 0 else (
            "blocked" if rolling_exact >= 2 else "needs_exact_timestamps"
        ),
    }
    if rolling["status"] == "blocked":
        blockers.append("two completed referral bonuses already fall within the rolling nine-day cap")
    elif rolling["status"] == "needs_exact_timestamps":
        blockers.append("obtain exact timestamps for recent completed referral bonuses to apply the rolling nine-day cap")

    tenure = referrer.get("tenure_days")
    if not isinstance(tenure, (int, float)) or isinstance(tenure, bool) or tenure < 0:
        tenure = None
    annual_count = referrer.get("annual_completed_bonus_count")
    if not isinstance(annual_count, int) or isinstance(annual_count, bool) or annual_count < 0:
        annual_count = None

    eligible, needs_confirmation, ineligible = [], [], []
    adult = referred.get("adult_confirmed")
    age = referred.get("age")
    for program in programs:
        required = ("name", "referrer_bonus", "referred_bonus", "annual_limit", "required_deposit",
                    "deposit_window_days", "referrer_tenure_days", "min_age")
        if not isinstance(program, dict) or any(field not in program for field in required):
            raise ValueError("each program must contain all required policy fields")
        name = program["name"]
        reasons, unknown = [], []
        if deposit < program["required_deposit"]:
            reasons.append("planned deposit is below the required deposit")
        if tenure is None:
            unknown.append("referrer first-checking-account tenure is not established")
        elif tenure < program["referrer_tenure_days"]:
            reasons.append("referrer does not meet the tenure requirement")
        if annual_count is None:
            unknown.append("applicable calendar-year completed-bonus count is not established")
        elif annual_count >= program["annual_limit"]:
            reasons.append("annual referral-bonus limit has been reached")

        max_age = program.get("max_age")
        if isinstance(age, (int, float)) and not isinstance(age, bool):
            if age < program["min_age"] or (max_age is not None and age > max_age):
                reasons.append("referred person does not meet the product age requirement")
        elif adult is True:
            if program["min_age"] > 18:
                unknown.append("referred person's exact age must be confirmed for this product")
            elif max_age is not None:
                unknown.append("referred person's age must be confirmed for this age-limited product")
        elif adult is False:
            if not program.get("minor_with_guardian_allowed"):
                reasons.append("referred person is below the adult minimum for this product")
            elif referred.get("light_green_guardian_eligible") is not True:
                unknown.append("guardian and Light Green age eligibility must be confirmed")
        else:
            unknown.append("referred person's age eligibility is not confirmed")

        item = {
            "program": name,
            "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
            "referrer_bonus": program["referrer_bonus"],
            "referred_bonus": program["referred_bonus"],
            "required_deposit": program["required_deposit"],
            "deposit_window_days": program["deposit_window_days"],
            "referrer_tenure_days": program["referrer_tenure_days"],
            "annual_limit": program["annual_limit"],
        }
        if reasons:
            item["reasons"] = reasons
            ineligible.append(item)
        elif unknown:
            item["conditions_to_confirm"] = unknown
            needs_confirmation.append(item)
        else:
            eligible.append(item)

    eligible.sort(key=lambda row: (-row["combined_bonus"], row["program"]))
    needs_confirmation.sort(key=lambda row: (-row["combined_bonus"], row["program"]))
    ineligible.sort(key=lambda row: (-row["combined_bonus"], row["program"]))
    recommendation = eligible[0] if not blockers and eligible else None
    return {
        "blocking_general_conditions": blockers,
        "rolling_window": rolling,
        "eligible_ranked": eligible,
        "needs_confirmation": needs_confirmation,
        "ineligible": ineligible,
        "recommendation": recommendation,
        "universal_conditions": [
            "qualifying deposit must be new money and remain for at least 30 days after the qualifying period ends",
            "referred account closed within 90 days may cause referral-bonus clawback",
            "both accounts must remain in good standing",
            "only one referral code and no other new-account promotion may be used",
        ],
    }


if __name__ == "__main__":
    try:
        emit(main(json.load(sys.stdin)))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        emit({"error": str(exc)})
        sys.exit(2)
