#!/usr/bin/env python3
"""Evaluate checking-referral eligibility from supplied, authoritative facts.

Input and output are JSON objects on stdin/stdout. No network or banking actions occur.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[1] / "references" / "referral_programs.json").read_text(encoding="utf-8"))["programs"]


def parse_datetime(value, exact=False):
    """Return aware datetime, or (None, explanatory error). Exact rejects date-only."""
    if not isinstance(value, str) or not value.strip():
        return None, "missing"
    text = value.strip()
    if exact and len(text) == 10:
        return None, "date-only timestamp is not exact"
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return None, "timestamp has no timezone"
        return parsed, None
    except ValueError:
        return None, "invalid ISO-8601 timestamp"


def parse_date_or_datetime(value):
    if not isinstance(value, str) or not value.strip():
        return None, "missing"
    try:
        text = value.strip().replace("Z", "+00:00")
        if len(text) == 10:
            return date.fromisoformat(text), None
        parsed = datetime.fromisoformat(text)
        return parsed.date(), None
    except ValueError:
        return None, "invalid ISO-8601 date or timestamp"


def bool_check(obj, field, label):
    value = obj.get(field)
    if value is True:
        return {"check": label, "state": "pass"}
    if value is False:
        return {"check": label, "state": "fail"}
    return {"check": label, "state": "unknown"}


def state_of(checks):
    states = [item["state"] for item in checks]
    if "fail" in states:
        return "fail"
    if "unknown" in states:
        return "unknown"
    return "pass"


def referral_program_key(referral, catalog_by_type):
    key = referral.get("program_key")
    if isinstance(key, str):
        return key
    return catalog_by_type.get(referral.get("referred_account_type"))


def main(payload):
    errors = []
    now, now_error = parse_datetime(payload.get("now"), exact=True)
    if now_error:
        errors.append("now: " + now_error)

    referrer = payload.get("referrer") if isinstance(payload.get("referrer"), dict) else {}
    recipient = payload.get("recipient") if isinstance(payload.get("recipient"), dict) else {}
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        errors.append("referrals must be an array")
        referrals = []

    catalog_by_type = {p["account_type"]: p["key"] for p in CATALOG}
    opening, opening_error = parse_date_or_datetime(referrer.get("earliest_checking_opened_at"))

    common = [
        bool_check(recipient, "same_registered_address", "recipient is registered at a different address"),
        bool_check(recipient, "new_customer_no_current_or_recent_account", "recipient is a new customer with no current or recently closed account"),
        bool_check(payload, "deposit_is_new_money", "planned qualifying deposit is new money"),
        {"check": "no other new-account promotion will be used", "state": "pass" if payload.get("uses_other_new_account_promotion") is False else ("fail" if payload.get("uses_other_new_account_promotion") is True else "unknown")}
    ]
    if recipient.get("is_business") is True:
        common.append(bool_check(recipient, "different_business_primary_owner", "business has a different primary owner"))
    elif recipient.get("is_business") is None:
        common.append({"check": "personal versus business referral is known", "state": "unknown"})

    # Rolling cap: only exact timestamps of actually received bonuses can prove it.
    rolling = {"check": "no more than two received referral bonuses in the rolling nine-day window", "state": "unknown", "received_bonus_count": None}
    annual_history = []
    timestamp_problem = False
    if now is not None:
        active_bonus_times = []
        for item in referrals:
            if not isinstance(item, dict) or item.get("status") != "COMPLETE":
                continue
            bonus_time, problem = parse_datetime(item.get("bonus_received_at"), exact=True)
            if problem:
                timestamp_problem = True
                continue
            if bonus_time > now:
                errors.append("a received bonus timestamp is in the future")
                continue
            # Conservative boundary: an event exactly nine days old remains in the window.
            if now - bonus_time <= timedelta(days=9):
                active_bonus_times.append(bonus_time)
            annual_history.append((item, bonus_time))
        if timestamp_problem:
            rolling["state"] = "unknown"
            rolling["detail"] = "one or more COMPLETE referrals lacks an exact bonus-received timestamp"
        else:
            rolling["received_bonus_count"] = len(active_bonus_times)
            rolling["state"] = "pass" if len(active_bonus_times) < 2 else "fail"
    common.append(rolling)

    deposit = payload.get("planned_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        deposit = None
        errors.append("planned_deposit must be a nonnegative number")

    program_results = []
    for program in CATALOG:
        checks = list(common)
        if opening_error:
            checks.append({"check": "referrer earliest checking opening date supports tenure", "state": "unknown", "detail": opening_error})
        else:
            days_held = (now.date() - opening).days if now else None
            checks.append({
                "check": "referrer meets %d-day tenure" % program["tenure_days"],
                "state": "pass" if days_held >= program["tenure_days"] else "fail",
                "days_held": days_held
            })
        checks.append({
            "check": "planned deposit meets $%s minimum" % program["deposit_required"],
            "state": "unknown" if deposit is None else ("pass" if deposit >= program["deposit_required"] else "fail")
        })

        count = sum(1 for item, stamp in annual_history if stamp.year == now.year and referral_program_key(item, catalog_by_type) == program["key"]) if now else None
        checks.append({
            "check": "annual completed-bonus count is below %d" % program["annual_cap"],
            "state": "unknown" if timestamp_problem or count is None else ("pass" if count < program["annual_cap"] else "fail"),
            "completed_bonus_count": count
        })

        age = recipient.get("age")
        if "recipient_min_age" in program:
            if not isinstance(age, int) or isinstance(age, bool):
                checks.append({"check": "recipient meets product age eligibility", "state": "unknown"})
            elif age < program["recipient_min_age"] or ("recipient_max_age" in program and age > program["recipient_max_age"]):
                checks.append({"check": "recipient meets product age eligibility", "state": "fail"})
            elif age < 18 and program.get("minor_requires_guardian"):
                checks.append(bool_check(recipient, "minor_has_guardian", "minor recipient has required guardian"))
            else:
                checks.append({"check": "recipient meets product age eligibility", "state": "pass"})
        else:
            if not isinstance(age, int) or isinstance(age, bool):
                checks.append({"check": "recipient is at least 18", "state": "unknown"})
            else:
                checks.append({"check": "recipient is at least 18", "state": "pass" if age >= 18 else "fail"})

        combined = program["referrer_bonus"] + program["recipient_bonus"]
        program_results.append({
            "program_key": program["key"], "account_type": program["account_type"],
            "referrer_bonus": program["referrer_bonus"], "recipient_bonus": program["recipient_bonus"],
            "combined_bonus": combined, "deposit_required": program["deposit_required"],
            "deposit_days": program["deposit_days"], "tenure_days": program["tenure_days"],
            "annual_cap": program["annual_cap"], "eligibility": state_of(checks), "checks": checks
        })

    eligible = [p for p in program_results if p["eligibility"] == "pass"]
    eligible.sort(key=lambda p: (-p["combined_bonus"], p["deposit_required"], p["account_type"]))
    unresolved = [p["account_type"] for p in program_results if p["eligibility"] == "unknown"]
    return {
        "recommendation_allowed": bool(eligible),
        "errors": errors,
        "common_checks": common,
        "ranked_candidates": eligible,
        "program_results": program_results,
        "unresolved_programs": unresolved,
        "universal_post_qualification_conditions": [
            "Qualifying deposit must remain for 30 days after the qualifying period ends.",
            "Both accounts must remain in good standing.",
            "A bonus may be clawed back if the referred account closes within 90 days of opening."
        ]
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level input must be an object")
        print(json.dumps(main(raw), sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"recommendation_allowed": False, "errors": ["invalid input: " + str(exc)]}, sort_keys=True))
