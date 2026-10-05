#!/usr/bin/env python3
"""Evaluate documented business referral programs from JSON stdin.

This program performs no banking action. It intentionally returns unresolved
results where runtime facts are absent or rolling-window timestamps are not exact.
"""
import json
import sys
from datetime import datetime, date, timedelta, timezone

PROGRAMS = [
    {"account": "World Blue", "bonus": 300, "deposit": 25000, "window_days": 90, "tenure_days": 90, "annual_limit": 12},
    {"account": "True Blue", "bonus": 350, "deposit": 50000, "window_days": 120, "tenure_days": 90, "annual_limit": 15},
    {"account": "Beige", "bonus": 500, "deposit": 100000, "window_days": 120, "tenure_days": 120, "annual_limit": 15},
    {"account": "Hunter Green", "bonus": 175, "deposit": 10000, "window_days": 90, "tenure_days": 60, "annual_limit": 10},
    {"account": "Lime Green", "bonus": 200, "deposit": 15000, "window_days": 90, "tenure_days": 90, "annual_limit": 12},
    {"account": "Navy Blue", "bonus": 100, "deposit": 5000, "window_days": 90, "tenure_days": 60, "annual_limit": 10},
    {"account": "Cobalt Blue", "bonus": 150, "deposit": 7500, "window_days": 90, "tenure_days": 60, "annual_limit": 10},
    {"account": "Sky Blue", "bonus": 150, "deposit": 10000, "window_days": 90, "tenure_days": 45, "annual_limit": 8},
]

GENERAL_CONFIRMATIONS = [
    "new_customer_no_accounts_or_recent_closure",
    "different_registered_address",
    "different_primary_owner_or_authorized_signer",
    "qualifying_deposit_is_new_money",
    "no_other_new_account_promotion",
]


def parse_now(value):
    if not isinstance(value, str):
        raise ValueError("now must be an ISO-8601 timestamp with an offset")
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("now must include a timezone offset")
    return parsed


def parse_referral_date(value):
    """Return (datetime-or-None, date, is_exact)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("each referral requires a nonempty date")
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            return parsed, parsed.date(), True
    except ValueError:
        pass
    try:
        day = date.fromisoformat(value.strip())
        return None, day, False
    except ValueError as exc:
        raise ValueError("referral date must be YYYY-MM-DD or ISO-8601") from exc


def canonical_account(value):
    text = str(value or "").lower().replace("account", "").strip()
    return " ".join(text.split())


def status_complete(item):
    return str(item.get("referral_status", item.get("status", ""))).upper() == "COMPLETE"


def rolling_state(now, completed):
    """Count exact events and conservatively flag date-only boundary ambiguity."""
    exact_within = []
    boundary_unknown = []
    for item in completed:
        parsed, day, exact = parse_referral_date(item.get("timestamp", item.get("date")))
        if exact:
            event = parsed.astimezone(now.tzinfo)
            age = now - event
            if timedelta(0) <= age <= timedelta(days=9):
                exact_within.append(item)
        else:
            day_difference = (now.date() - day).days
            if 0 <= day_difference <= 8:
                exact_within.append(item)
            elif day_difference == 9:
                boundary_unknown.append(item)
    if len(exact_within) >= 2:
        state = "blocked"
    elif len(exact_within) + len(boundary_unknown) >= 2:
        state = "unresolved"
    else:
        state = "clear"
    return {
        "state": state,
        "successful_bonuses_definitely_within_nine_days": len(exact_within),
        "date_only_events_at_nine_day_boundary": len(boundary_unknown),
        "reason": (
            "Two or more successful bonuses are within the rolling nine-day window."
            if state == "blocked" else
            "Exact timestamps are required to determine whether date-only events at the nine-day boundary are still in the rolling window."
            if state == "unresolved" else
            "Fewer than two successful bonuses are definitely within the rolling nine-day window."
        ),
    }


def main(payload):
    errors = []
    try:
        now = parse_now(payload.get("now"))
    except ValueError as exc:
        return {"errors": [str(exc)], "recommendation": None}

    deposit = payload.get("planned_qualifying_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        errors.append("planned_qualifying_deposit must be a nonnegative number representing total planned new money during the qualifying window")

    tenure = payload.get("referrer_tenure_days")
    if not isinstance(tenure, (int, float)) or isinstance(tenure, bool) or tenure < 0:
        errors.append("referrer_tenure_days must be a nonnegative number measured from the earliest checking account opening")

    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        errors.append("referrals must be a list containing all known referral records")
        referrals = []

    confirmations = payload.get("confirmations")
    if not isinstance(confirmations, dict):
        errors.append("confirmations must be an object")
        confirmations = {}

    completed = []
    for index, item in enumerate(referrals):
        if not isinstance(item, dict):
            errors.append("referrals[%d] must be an object" % index)
            continue
        if status_complete(item):
            try:
                parse_referral_date(item.get("timestamp", item.get("date")))
                completed.append(item)
            except ValueError as exc:
                errors.append("referrals[%d]: %s" % (index, exc))

    if errors:
        return {"errors": errors, "recommendation": None}

    rolling = rolling_state(now, completed)
    global_blockers = []
    for key in GENERAL_CONFIRMATIONS:
        value = confirmations.get(key)
        if value is not True:
            description = key.replace("_", " ")
            prefix = "not satisfied" if value is False else "not confirmed"
            global_blockers.append("General eligibility %s: %s." % (prefix, description))
    if rolling["state"] != "clear":
        global_blockers.append(rolling["reason"])

    eligible = []
    ineligible = []
    current_year = now.year
    for program in PROGRAMS:
        reasons = []
        account_key = canonical_account(program["account"])
        annual_count = 0
        for item in completed:
            _, item_day, _ = parse_referral_date(item.get("timestamp", item.get("date")))
            if item_day.year == current_year and canonical_account(item.get("referred_account_type")) == account_key:
                annual_count += 1
        if annual_count >= program["annual_limit"]:
            reasons.append("annual limit reached (%d of %d)" % (annual_count, program["annual_limit"]))
        if deposit < program["deposit"]:
            reasons.append("planned qualifying deposit is below $%s" % format(program["deposit"], ","))
        if tenure < program["tenure_days"]:
            reasons.append("earliest-checking tenure is below %d days" % program["tenure_days"])
        if program["account"] == "Sky Blue" and confirmations.get("sky_blue_startup_within_four_years") is not True:
            reasons.append("Sky Blue startup-within-four-years condition is not confirmed" if confirmations.get("sky_blue_startup_within_four_years") is None else "Sky Blue startup-within-four-years condition is not satisfied")

        result = dict(program)
        result["annual_successful_referrals_counted"] = annual_count
        if reasons:
            result["reasons"] = reasons
            ineligible.append(result)
        else:
            eligible.append(result)

    eligible.sort(key=lambda candidate: (-candidate["bonus"], candidate["deposit"], candidate["account"]))
    recommendation = None
    if not global_blockers and eligible:
        top = eligible[0]
        recommendation = {
            "account": top["account"],
            "referrer_bonus": top["bonus"],
            "qualifying_deposit": top["deposit"],
            "deposit_window_days": top["window_days"],
            "minimum_referrer_tenure_days": top["tenure_days"],
            "annual_limit": top["annual_limit"],
            "message": "Highest documented referrer bonus among candidates supported by the supplied confirmed facts.",
        }

    return {
        "errors": [],
        "recommendation": recommendation,
        "global_blockers": global_blockers,
        "rolling_window": rolling,
        "eligible_candidates": eligible,
        "ineligible_candidates": ineligible,
        "post_qualification_conditions": [
            "The qualifying deposit must remain for at least 30 days after the qualifying period ends.",
            "A bonus may be clawed back if the referred account closes within 90 days of opening.",
            "Both accounts must remain in good standing for bonuses to be paid.",
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be one JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"errors": [str(exc)], "recommendation": None}, sort_keys=True))
