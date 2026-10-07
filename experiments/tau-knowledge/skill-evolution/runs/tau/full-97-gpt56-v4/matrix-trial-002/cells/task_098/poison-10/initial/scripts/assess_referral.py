#!/usr/bin/env python3
"""Assess checking-referral prerequisites and rank fully qualified programs.

Reads one JSON object from stdin. Writes one JSON object to stdout. It makes no
network calls and does not perform banking actions.
"""
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

PROGRAM_FILE = Path(__file__).resolve().parent.parent / "references" / "referral_programs.json"


def parse_datetime(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO-8601 timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed


def parse_date(value, field):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def bool_state(data, key, required=True):
    value = data.get(key)
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "unknown" if required else "pass"


def main(data):
    config = json.loads(PROGRAM_FILE.read_text(encoding="utf-8"))
    programs = config["programs"]
    rules = config["general_rules"]
    blockers = []

    # Identity is deliberately a hard gate for presenting referral information.
    if bool_state(data, "identity_verified") != "pass":
        blockers.append("Referrer identity has not been verified with two profile fields.")

    now = None
    try:
        now = parse_datetime(data.get("now"), "now")
    except ValueError as exc:
        blockers.append(str(exc))

    opened = None
    try:
        opened = parse_date(data.get("earliest_checking_opened"), "earliest_checking_opened")
    except ValueError as exc:
        blockers.append(str(exc))
    if opened is None:
        blockers.append("The opening date of the earliest Rho-Bank checking account is unknown.")

    # Exact timestamps are essential; date-only referral history cannot prove this rule.
    timestamps = data.get("recent_successful_bonus_timestamps")
    recent_count = None
    if not isinstance(timestamps, list):
        blockers.append("Exact timestamps for all recent successful referral bonuses are unavailable.")
    elif now is not None:
        try:
            parsed = [parse_datetime(x, "recent_successful_bonus_timestamps entry") for x in timestamps]
            window_start = now - timedelta(days=rules["rolling_window_days"])
            recent_count = sum(window_start <= item <= now for item in parsed)
            if recent_count >= rules["rolling_successful_bonus_cap"]:
                blockers.append("The referrer already has two successful bonuses in the rolling nine-day window.")
        except ValueError as exc:
            blockers.append(str(exc))

    universal_checks = [
        ("prospect_new_customer_confirmed", "The proposed customer has not confirmed new-customer status and the 12-month closed-account restriction."),
        ("different_registered_address_confirmed", "Different registered addresses have not been confirmed."),
        ("new_money_confirmed", "The qualifying deposit has not been confirmed as new money."),
        ("no_other_promotion_confirmed", "It has not been confirmed that no other new-account promotion will be used."),
        ("one_referral_code_confirmed", "It has not been confirmed that only one referral code will be used."),
        ("referrer_good_standing_confirmed", "The referrer's good-standing status has not been confirmed.")
    ]
    for key, message in universal_checks:
        state = bool_state(data, key)
        if state != "pass":
            blockers.append(message)

    deposit = data.get("candidate_deposit_amount")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        blockers.append("A nonnegative intended qualifying-deposit amount is required.")
        deposit = None

    age = data.get("candidate_age")
    if age is not None and (not isinstance(age, (int, float)) or isinstance(age, bool) or age < 0):
        blockers.append("candidate_age must be a nonnegative number when supplied.")
        age = None
    guardian = bool_state(data, "guardian_for_minor_confirmed") == "pass"

    annual_counts = data.get("annual_successful_bonus_count_by_program")
    if not isinstance(annual_counts, dict):
        annual_counts = {}
        blockers.append("Current-calendar-year successful-bonus counts by program are unavailable.")

    eligible = []
    conditional = []
    for program in programs:
        reasons = []
        if deposit is None or deposit < program["deposit_required"]:
            reasons.append(f"Requires at least ${program['deposit_required']:,} in new money.")
        if opened is None or now is None:
            reasons.append("Earliest checking-account opening date must be verified.")
        elif (now.date() - opened).days < program["tenure_days"]:
            reasons.append(f"Requires {program['tenure_days']} days of checking tenure.")

        count = annual_counts.get(program["name"])
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            reasons.append("Current-calendar-year successful-bonus count for this program is required.")
        elif count >= program["annual_cap"]:
            reasons.append(f"Annual cap of {program['annual_cap']} successful bonuses has been reached.")

        if "min_age" in program:
            if age is None:
                reasons.append("Proposed customer's age must be confirmed.")
            elif age < program["min_age"]:
                reasons.append(f"Primary holder must be at least {program['min_age']}.")
            elif "max_age" in program and age > program["max_age"]:
                reasons.append(f"Primary holder must be no older than {program['max_age']}.")
            elif age < 18 and program.get("minor_guardian_required") and not guardian:
                reasons.append("A guardian is required for a minor Light Green applicant.")

        option = {
            "program": program["name"],
            "referrer_bonus": program["referrer_bonus"],
            "new_member_bonus": program["new_member_bonus"],
            "combined_bonus": program["referrer_bonus"] + program["new_member_bonus"],
            "deposit_required": program["deposit_required"],
            "deposit_days": program["deposit_days"],
            "tenure_days": program["tenure_days"],
            "annual_cap": program["annual_cap"]
        }
        if "min_age" in program:
            option["min_age"] = program["min_age"]
        if "max_age" in program:
            option["max_age"] = program["max_age"]

        if reasons:
            option["unresolved_conditions"] = reasons
            conditional.append(option)
        elif not blockers:
            eligible.append(option)
        else:
            # It is otherwise product-qualified, but a global prerequisite prevents advice.
            option["unresolved_conditions"] = ["Universal referral prerequisites remain unresolved."]
            conditional.append(option)

    eligible.sort(key=lambda x: (-x["combined_bonus"], x["program"]))
    conditional.sort(key=lambda x: (-x["combined_bonus"], x["program"]))
    return {
        "eligible_to_recommend": bool(eligible) and not blockers,
        "blockers": blockers,
        "rolling_window_successful_bonus_count": recent_count,
        "eligible_options": eligible,
        "conditional_options": conditional,
        "recommended_option": eligible[0] if eligible and not blockers else None,
        "notes": [
            "A successful referred account must keep the qualifying new-money deposit for at least 30 days after the qualifying period ends.",
            "Closing the referred account within 90 days may cause a referral-bonus clawback; both accounts must remain in good standing."
        ]
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
