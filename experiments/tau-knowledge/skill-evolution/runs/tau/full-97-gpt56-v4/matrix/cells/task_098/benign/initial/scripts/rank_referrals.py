#!/usr/bin/env python3
"""Rank supported checking-referral programs from supplied, verified facts.

Input: one JSON object on stdin. See SKILL.md for the schema.
Output: one JSON object on stdout. Errors are JSON on stderr and exit status 2.
"""
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "referral_programs.json"
AGE_GROUPS = {
    "13-17": (13, 17),
    "18-24": (18, 24),
    "25-61": (25, 61),
    "62+": (62, None),
}


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True), file=sys.stderr)
    raise SystemExit(2)


def parse_current(value):
    if not isinstance(value, str):
        fail("current_time must be an ISO-8601 datetime string")
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        fail("current_time is not a valid ISO-8601 datetime")
    if parsed.tzinfo is None:
        fail("current_time must include a UTC offset or timezone")
    return parsed


def parse_completed_at(value, tzinfo):
    if not isinstance(value, str):
        fail("successful_referrals.completed_at must be a string")
    # A bare date is deliberately retained as imprecise rather than assumed midnight.
    try:
        if len(value) == 10:
            return (date.fromisoformat(value), True)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("successful_referrals.completed_at must be ISO date or datetime")
    if parsed.tzinfo is None:
        fail("successful_referrals.completed_at datetime must include timezone")
    return (parsed.astimezone(tzinfo), False)


def group_can_meet_age(group, minimum, maximum):
    low, high = AGE_GROUPS[group]
    if high is not None and high < minimum:
        return False
    if maximum is not None and low > maximum:
        return False
    # A broad group that straddles a boundary is not proof of eligibility.
    if low < minimum or (maximum is not None and (high is None or high > maximum)):
        return None
    return True


def completed_year_count(history, account_type, current_year):
    count = 0
    for item in history:
        completed, date_only = item["parsed_time"]
        item_year = completed.year if not date_only else completed.year
        if item["account_type"] == account_type and item_year == current_year:
            count += 1
    return count


def rolling_assessment(history, now, window_days):
    definite = 0
    ambiguous = 0
    boundary_dates = []
    cutoff = now - timedelta(days=window_days)
    for item in history:
        completed, date_only = item["parsed_time"]
        if not date_only:
            if cutoff <= completed <= now:
                definite += 1
            continue
        # With a date only: <=8 calendar days is certainly in; >=10 is certainly out.
        difference = (now.date() - completed).days
        if 0 <= difference <= window_days - 1:
            definite += 1
        elif difference == window_days:
            ambiguous += 1
            boundary_dates.append(completed.isoformat())
    if definite >= 2:
        state = "blocked"
    elif definite + ambiguous >= 2:
        state = "undetermined"
    else:
        state = "not_blocked"
    return {
        "state": state,
        "definitely_within_window": definite,
        "boundary_date_only_records": boundary_dates,
        "message": (
            "Two or more completed bonuses are definitely in the rolling window."
            if state == "blocked" else
            "Date-only records on the nine-day boundary prevent an exact rolling-window determination."
            if state == "undetermined" else
            "The supplied completed-bonus history does not establish that the rolling cap is reached."
        )
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one valid JSON object: " + str(exc))
    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    now = parse_current(payload.get("current_time"))
    tenure = payload.get("referrer_tenure_days")
    if tenure is not None and (not isinstance(tenure, int) or isinstance(tenure, bool) or tenure < 0):
        fail("referrer_tenure_days must be a nonnegative integer or null")
    age_group = payload.get("recipient_age_group")
    if age_group is not None and age_group not in AGE_GROUPS:
        fail("recipient_age_group must be one of 13-17, 18-24, 25-61, 62+, or null")
    deposit = payload.get("planned_new_money_deposit")
    if deposit is not None and (not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0):
        fail("planned_new_money_deposit must be a nonnegative number or null")

    history_raw = payload.get("successful_referrals", [])
    if not isinstance(history_raw, list):
        fail("successful_referrals must be an array")
    history = []
    for raw in history_raw:
        if not isinstance(raw, dict) or not isinstance(raw.get("account_type"), str):
            fail("each successful_referrals item must contain string account_type and completed_at")
        parsed, date_only = parse_completed_at(raw.get("completed_at"), now.tzinfo)
        history.append({"account_type": raw["account_type"], "parsed_time": (parsed, date_only)})

    with CATALOG_PATH.open(encoding="utf-8") as source:
        catalog = json.load(source)
    programs = catalog["programs"]
    names = [p["account_type"] for p in programs]
    if len(names) != len(set(names)):
        fail("catalog has duplicate account_type entries")

    rules = catalog["general_rules"]
    rolling = rolling_assessment(history, now, rules["rolling_window_days"])
    general_confirmations = {
        "new_customer_confirmed": payload.get("new_customer_confirmed", False) is True,
        "different_registered_address_confirmed": payload.get("different_registered_address_confirmed", False) is True,
        "no_other_promotion": payload.get("no_other_promotion", False) is True,
    }
    guardian = payload.get("guardian_for_minor", False) is True

    results = []
    for program in programs:
        blockers = []
        missing = []
        if rolling["state"] == "blocked":
            blockers.append("rolling_nine_day_cap_reached")
        elif rolling["state"] == "undetermined":
            missing.append("exact_completed_bonus_timestamps_for_rolling_window")

        annual_count = completed_year_count(history, program["account_type"], now.year)
        if annual_count >= program["annual_cap"]:
            blockers.append("annual_cap_reached")

        if tenure is None:
            missing.append("referrer_earliest_checking_open_date")
        elif tenure < program["referrer_tenure_days"]:
            blockers.append("referrer_tenure_too_short")

        if age_group is None:
            missing.append("recipient_age_group")
        else:
            age_ok = group_can_meet_age(age_group, program["recipient_min_age"], program["recipient_max_age"])
            if age_ok is False:
                blockers.append("recipient_age_not_eligible_for_account")
            elif age_ok is None:
                missing.append("recipient_exact_age_within_reported_range")
            if program.get("minor_requires_guardian") and age_group == "13-17" and not guardian:
                missing.append("guardian_confirmation_for_minor")

        if deposit is None:
            missing.append("planned_new_money_deposit")
        elif deposit < program["qualifying_deposit"]:
            blockers.append("planned_deposit_below_qualifying_minimum")

        for key, confirmed in general_confirmations.items():
            if not confirmed:
                missing.append(key)

        if blockers:
            state = "ineligible"
        elif missing:
            state = "conditional"
        else:
            state = "qualified"
        results.append({
            "account_type": program["account_type"],
            "state": state,
            "combined_bonus": program["referrer_bonus"] + program["new_member_bonus"],
            "referrer_bonus": program["referrer_bonus"],
            "new_member_bonus": program["new_member_bonus"],
            "qualifying_deposit": program["qualifying_deposit"],
            "deposit_deadline_days": program["deposit_deadline_days"],
            "referrer_tenure_days": program["referrer_tenure_days"],
            "recipient_min_age": program["recipient_min_age"],
            "recipient_max_age": program["recipient_max_age"],
            "annual_completed_count": annual_count,
            "annual_cap": program["annual_cap"],
            "blockers": sorted(set(blockers)),
            "missing_facts": sorted(set(missing))
        })

    order = {"qualified": 0, "conditional": 1, "ineligible": 2}
    results.sort(key=lambda item: (order[item["state"]], -item["combined_bonus"], item["account_type"]))
    qualified = [item for item in results if item["state"] == "qualified"]
    conditional = [item for item in results if item["state"] == "conditional"]

    if rolling["state"] == "blocked":
        referrer_status = "not_eligible"
    elif tenure is None:
        referrer_status = "undetermined"
    elif tenure < min(p["referrer_tenure_days"] for p in programs):
        referrer_status = "not_eligible"
    elif rolling["state"] == "undetermined":
        referrer_status = "undetermined"
    else:
        referrer_status = "eligible_for_at_least_one_program_subject_to_program_conditions"

    output = {
        "referrer_submission_status": referrer_status,
        "rolling_window": rolling,
        "best_qualified": qualified[0] if qualified else None,
        "best_conditional": conditional[0] if conditional else None,
        "programs": results,
        "general_conditions_not_modeled_as_account_specific": [
            "Qualifying deposit must be new money and remain at least 30 days after the qualifying period.",
            "Both accounts must remain in good standing; a bonus may be clawed back if the referred account closes within 90 days.",
            "Only one referral code may be applied and referral bonuses cannot stack with new-account promotions."
        ]
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
