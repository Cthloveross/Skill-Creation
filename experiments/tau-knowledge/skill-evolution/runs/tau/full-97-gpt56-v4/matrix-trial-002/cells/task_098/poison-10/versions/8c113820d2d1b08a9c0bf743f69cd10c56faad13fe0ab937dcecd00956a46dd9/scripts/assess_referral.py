#!/usr/bin/env python3
"""Assess checking-referral eligibility without performing any banking action.

Input: one JSON object on stdin, documented in SKILL.md.
Output: one JSON object on stdout. Invalid input emits {"error": ...} and exits 2.
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROGRAM_FILE = Path(__file__).resolve().parent.parent / "references" / "referral_programs.json"


def parse_now(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("now must be a nonempty ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        raise ValueError("now must include a timezone offset")
    return result


def parse_date(value, field):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def parse_timestamp(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return result


def confirmed(data, key):
    """Return pass/fail/unknown, without treating truthy strings as confirmation."""
    value = data.get(key)
    return "pass" if value is True else "fail" if value is False else "unknown"


def rolling_status(events, now, days, cap):
    """Return (count, ambiguous, errors) for COMPLETE bonus events.

    A date-only event within the last nine calendar days might be either side of
    the exact timestamp boundary, so it cannot prove the rolling result.
    """
    if not isinstance(events, list):
        return None, True, ["Successful referral-bonus events are unavailable."]
    count = 0
    ambiguous = False
    errors = []
    start = now - timedelta(days=days)
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"successful_bonus_events[{index}] must be an object.")
            continue
        if event.get("status") not in (None, "COMPLETE"):
            continue
        if "timestamp" in event and event["timestamp"] not in (None, ""):
            try:
                moment = parse_timestamp(event["timestamp"], f"successful_bonus_events[{index}].timestamp")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if start <= moment <= now:
                count += 1
        elif "date" in event and event["date"] not in (None, ""):
            try:
                event_day = parse_date(event["date"], f"successful_bonus_events[{index}].date")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            # Any event dated strictly before (now.date - 9 days) is safely old;
            # dates on/after it need an exact time to decide.
            if event_day >= (now.date() - timedelta(days=days)):
                ambiguous = True
        else:
            errors.append(f"successful_bonus_events[{index}] needs timestamp or date.")
    if count >= cap:
        return count, ambiguous, errors
    return count, ambiguous, errors


def option(program):
    result = {
        "program": program["name"],
        "referrer_bonus": program["referrer_bonus"],
        "new_member_bonus": program["new_member_bonus"],
        "combined_bonus": program["referrer_bonus"] + program["new_member_bonus"],
        "deposit_required": program["deposit_required"],
        "deposit_days": program["deposit_days"],
        "tenure_days": program["tenure_days"],
        "annual_cap": program["annual_cap"],
    }
    for key in ("min_age", "max_age"):
        if key in program:
            result[key] = program[key]
    return result


def assess(data):
    config = json.loads(PROGRAM_FILE.read_text(encoding="utf-8"))
    rules = config["general_rules"]
    programs = config["programs"]
    blockers = []

    try:
        now = parse_now(data.get("now"))
    except ValueError as exc:
        now = None
        blockers.append(str(exc))
    try:
        opened = parse_date(data.get("earliest_checking_opened"), "earliest_checking_opened")
    except ValueError as exc:
        opened = None
        blockers.append(str(exc))
    if opened is None:
        blockers.append("The opening date of the earliest Rho-Bank checking account is unknown.")

    rolling_count = None
    if now is not None:
        rolling_count, rolling_ambiguous, event_errors = rolling_status(
            data.get("successful_bonus_events"), now,
            rules["rolling_window_days"], rules["rolling_successful_bonus_cap"],
        )
        blockers.extend(event_errors)
        if rolling_ambiguous:
            blockers.append("Exact timestamps are needed to confirm the rolling nine-day successful-bonus limit.")
        if rolling_count is not None and rolling_count >= rules["rolling_successful_bonus_cap"]:
            blockers.append("The referrer already has two successful bonuses in the rolling nine-day window.")

    global_fields = (
        ("prospect_new_customer_confirmed", "The prospective customer has not confirmed new-customer status and the 12-month closed-account restriction."),
        ("different_registered_address_confirmed", "Different registered addresses have not been confirmed."),
        ("new_money_confirmed", "The qualifying deposit has not been confirmed as new money."),
        ("no_other_promotion_confirmed", "It has not been confirmed that no other new-account promotion will be used."),
        ("one_referral_code_confirmed", "It has not been confirmed that only one referral code will be used."),
        ("referrer_good_standing_confirmed", "The referrer's good-standing status has not been confirmed."),
    )
    for field, message in global_fields:
        if confirmed(data, field) != "pass":
            blockers.append(message)

    deposit = data.get("candidate_deposit_amount")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        deposit = None
        blockers.append("A nonnegative intended qualifying-deposit amount is required.")
    age = data.get("candidate_age")
    if age is not None and (not isinstance(age, (int, float)) or isinstance(age, bool) or age < 0):
        age = None
        blockers.append("candidate_age must be a nonnegative number when supplied.")
    guardian = confirmed(data, "guardian_for_minor_confirmed") == "pass"

    annual = data.get("annual_successful_bonus_count_by_program")
    if not isinstance(annual, dict):
        annual = {}
        blockers.append("Current-calendar-year successful-bonus counts by program are unavailable.")

    eligible, conditional = [], []
    for program in programs:
        reasons = []
        if deposit is None or deposit < program["deposit_required"]:
            reasons.append(f"Requires at least ${program['deposit_required']:,} in new money.")
        if now is None or opened is None:
            reasons.append("Earliest checking-account opening date must be verified.")
        elif (now.date() - opened).days < program["tenure_days"]:
            reasons.append(f"Requires {program['tenure_days']} days of checking tenure.")
        count = annual.get(program["name"])
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            reasons.append("Current-calendar-year successful-bonus count for this program is required.")
        elif count >= program["annual_cap"]:
            reasons.append(f"Annual cap of {program['annual_cap']} successful bonuses has been reached.")
        if "min_age" in program:
            if age is None:
                reasons.append("Proposed customer's age must be confirmed.")
            elif age < program["min_age"] or age > program.get("max_age", float("inf")):
                reasons.append("Proposed customer does not meet this account's age requirement.")
            elif age < 18 and program.get("minor_guardian_required") and not guardian:
                reasons.append("A guardian must be confirmed for a minor Light Green applicant.")
        item = option(program)
        if not reasons and not blockers:
            eligible.append(item)
        else:
            item["unresolved_conditions"] = reasons or ["Universal referral prerequisites remain unresolved."]
            conditional.append(item)

    eligible.sort(key=lambda x: (-x["combined_bonus"], x["program"]))
    conditional.sort(key=lambda x: (-x["combined_bonus"], x["program"]))
    return {
        "eligible_to_recommend": bool(eligible) and not blockers,
        "blockers": blockers,
        "rolling_window_successful_bonus_count": rolling_count,
        "eligible_options": eligible,
        "conditional_options": conditional,
        "recommended_option": eligible[0] if eligible and not blockers else None,
        "notes": [
            "The qualifying new-money deposit must remain for at least 30 days after the qualifying period ends.",
            "Closing the referred account within 90 days may cause a referral-bonus clawback; both accounts must remain in good standing.",
        ],
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(assess(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
