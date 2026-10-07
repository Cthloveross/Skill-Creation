"""Evaluate checking-referral eligibility from JSON stdin and emit JSON stdout.

Input schema is documented in SKILL.md. This script performs no banking action and
uses only supplied facts. Unknown facts should be omitted or set to null.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

PROGRAMS = (
    {"account_type": "Blue Account", "referrer_bonus": 35, "member_bonus": 30,
     "deposit": 500, "deposit_days": 60, "tenure_days": 30, "annual_cap": 5},
    {"account_type": "Green Fee-Free Account", "referrer_bonus": 20, "member_bonus": 35,
     "deposit": 300, "deposit_days": 60, "tenure_days": 30, "annual_cap": 4},
    {"account_type": "Light Blue Account", "referrer_bonus": 30, "member_bonus": 20,
     "deposit": 500, "deposit_days": 60, "tenure_days": 30, "annual_cap": 5},
    {"account_type": "Light Green Account", "referrer_bonus": 15, "member_bonus": 25,
     "deposit": 100, "deposit_days": 90, "tenure_days": 14, "annual_cap": 3,
     "age_min": 13, "age_max": 24, "guardian_for_minor": True},
    {"account_type": "Green Account (checking)", "referrer_bonus": 20, "member_bonus": 30,
     "deposit": 500, "deposit_days": 60, "tenure_days": 30, "annual_cap": 5},
    {"account_type": "Evergreen Account", "referrer_bonus": 35, "member_bonus": 25,
     "deposit": 750, "deposit_days": 60, "tenure_days": 45, "annual_cap": 6},
    {"account_type": "Dark Green Account", "referrer_bonus": 40, "member_bonus": 30,
     "deposit": 1000, "deposit_days": 60, "tenure_days": 45, "annual_cap": 6},
    {"account_type": "Gold Years Account", "referrer_bonus": 50, "member_bonus": 75,
     "deposit": 1000, "deposit_days": 90, "tenure_days": 30, "annual_cap": 6,
     "age_min": 62},
    {"account_type": "Bluest Account", "referrer_bonus": 75, "member_bonus": 50,
     "deposit": 2000, "deposit_days": 90, "tenure_days": 60, "annual_cap": 8},
)

REQUIRED_CANDIDATE_FIELDS = (
    "referred_age", "new_customer_12m", "different_registered_address",
    "planned_deposit", "deposit_new_money", "other_new_account_promotion",
    "one_referral_code",
)


def parse_timestamp(value):
    """Return an aware datetime, or None for missing, date-only, or invalid input."""
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def missing_fields(data):
    missing = []
    referrer = data.get("referrer")
    candidate = data.get("candidate")
    if not isinstance(referrer, dict) or referrer.get("tenure_days") is None:
        missing.append("referrer's earliest checking-account tenure in days")
    if not isinstance(candidate, dict):
        return missing + ["prospective referred person's eligibility details"]
    for field in REQUIRED_CANDIDATE_FIELDS:
        if candidate.get(field) is None:
            missing.append("candidate." + field)
    age = candidate.get("referred_age")
    if isinstance(age, (int, float)) and 13 <= age < 18 and candidate.get("guardian_present") is None:
        missing.append("candidate.guardian_present for a minor Light Green referral")
    if data.get("referral_history_complete") is not True:
        missing.append("complete referral-bonus history for annual and rolling-limit checks")
    if parse_timestamp(data.get("now")) is None:
        missing.append("current timezone-aware timestamp")
    events = data.get("referral_events")
    if not isinstance(events, list):
        missing.append("referral_events")
    elif any(e.get("status") == "COMPLETE" and parse_timestamp(e.get("bonus_timestamp")) is None
             for e in events if isinstance(e, dict)):
        missing.append("exact timezone-aware bonus timestamps for COMPLETE referrals")
    return missing


def common_reasons(candidate, completed_in_window):
    reasons = []
    if candidate.get("new_customer_12m") is not True:
        reasons.append("referred person is not confirmed as a new customer with no current or past-12-month closed Rho-Bank account")
    if candidate.get("different_registered_address") is not True:
        reasons.append("referrer and referred person must have different registered addresses")
    if candidate.get("deposit_new_money") is not True:
        reasons.append("qualifying deposit must be new money, not a transfer from another Rho-Bank account")
    if candidate.get("other_new_account_promotion") is not False:
        reasons.append("referral bonus cannot be combined with another new-account promotion")
    if candidate.get("one_referral_code") is not True:
        reasons.append("only one referral code may be applied per new account")
    if completed_in_window >= 2:
        reasons.append("already received two referral bonuses in the rolling nine-day window")
    return reasons


def evaluate(data):
    missing = missing_fields(data)
    if missing:
        return {"status": "blocked_missing_information", "missing_information": missing,
                "shared_reasons": [], "eligible_candidates": [], "ineligible_candidates": []}

    now = parse_timestamp(data["now"]).astimezone(timezone.utc)
    candidate = data["candidate"]
    tenure = data["referrer"]["tenure_days"]
    events = data["referral_events"]
    # Inclusive boundary is conservative: a bonus exactly nine days ago still counts.
    lower_bound = now - timedelta(days=9)
    completed = []
    for event in events:
        if not isinstance(event, dict) or event.get("status") != "COMPLETE":
            continue
        when = parse_timestamp(event.get("bonus_timestamp")).astimezone(timezone.utc)
        completed.append((event, when))
    in_window = [e for e, when in completed if lower_bound <= when <= now]
    shared = common_reasons(candidate, len(in_window))
    annual_counts = {}
    for event, when in completed:
        if when.year == now.year:
            key = event.get("account_type")
            annual_counts[key] = annual_counts.get(key, 0) + 1

    eligible, ineligible = [], []
    for program in PROGRAMS:
        reasons = list(shared)
        age = candidate["referred_age"]
        # General referrals require adulthood except qualifying Light Green minors.
        if program["account_type"] != "Light Green Account" and age < 18:
            reasons.append("referred person must be at least 18 for this account referral")
        if "age_min" in program and age < program["age_min"]:
            reasons.append("referred person does not meet the account's minimum age")
        if "age_max" in program and age > program["age_max"]:
            reasons.append("referred person exceeds the account's maximum age")
        if program.get("guardian_for_minor") and age < 18 and candidate.get("guardian_present") is not True:
            reasons.append("a guardian is required for a minor Light Green referral")
        if tenure < program["tenure_days"]:
            reasons.append("referrer has not met the %d-day tenure requirement" % program["tenure_days"])
        if candidate["planned_deposit"] < program["deposit"]:
            reasons.append("planned deposit is below the $%d qualifying-deposit requirement" % program["deposit"])
        if annual_counts.get(program["account_type"], 0) >= program["annual_cap"]:
            reasons.append("annual referral-bonus cap for this account has been reached")
        result = {
            "account_type": program["account_type"],
            "referrer_bonus": program["referrer_bonus"],
            "member_bonus": program["member_bonus"],
            "combined_bonus": program["referrer_bonus"] + program["member_bonus"],
            "qualifying_deposit": program["deposit"],
            "deposit_window_days": program["deposit_days"],
        }
        if reasons:
            result["reasons"] = reasons
            ineligible.append(result)
        else:
            eligible.append(result)
    eligible.sort(key=lambda item: (-item["combined_bonus"], item["account_type"]))
    return {
        "status": "eligible_candidates" if eligible else "no_eligible_candidates",
        "missing_information": [],
        "shared_reasons": shared,
        "eligible_candidates": eligible,
        "ineligible_candidates": ineligible,
        "rolling_complete_bonus_count": len(in_window),
    }


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "input_error", "error": str(exc)}))


if __name__ == "__main__":
    main()
