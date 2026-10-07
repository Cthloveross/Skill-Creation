#!/usr/bin/env python3
"""Deterministically audit checking referral capacity from supplied, authorized facts.

Reads one JSON object on stdin and writes a JSON object on stdout.  It never
retrieves customer data or authorizes a referral.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone

PROGRAMS = {
    "Dark Green Account": {"tenure_days": 45, "annual_cap": 6},
    "Gold Years Account": {"tenure_days": 30, "annual_cap": 6},
    "Sky Blue Account": {"tenure_days": 45, "annual_cap": 8},
}


def parse_temporal(value):
    """Return (UTC datetime, has_explicit_time), or (None, False)."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    text = value.strip()
    try:
        if "T" in text or " " in text:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc), True
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc), False
    except ValueError:
        for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc), False
            except ValueError:
                continue
    return None, False


def confirmed(mapping, key):
    return mapping.get(key) is True


def annual_count(referrals, program, year):
    return sum(
        1 for item in referrals
        if isinstance(item, dict)
        and item.get("referred_account_type") == program
        and item.get("referral_status") == "COMPLETE"
        and (parse_temporal(item.get("date"))[0] is not None)
        and parse_temporal(item.get("date"))[0].year == year
    )


def rolling_summary(referrals, as_of):
    # The policy is timestamp based. Date-only records can identify a possible
    # in-window bonus but cannot conclusively resolve the boundary.
    start = as_of - timedelta(days=9)
    exact_records = []
    date_only_records = []
    invalid_dates = 0
    for item in referrals:
        if not isinstance(item, dict) or item.get("referral_status") != "COMPLETE":
            continue
        when, has_time = parse_temporal(item.get("date"))
        if when is None:
            invalid_dates += 1
        elif has_time and start <= when <= as_of:
            exact_records.append(item)
        elif not has_time and start.date() <= when.date() <= as_of.date():
            date_only_records.append(item)
    observed = len(exact_records) + len(date_only_records)
    return {
        "window_start": start.isoformat(),
        "as_of": as_of.isoformat(),
        "complete_bonus_count_observed": observed,
        "slots_if_observed_count_is_final": max(0, 2 - observed),
        "exact": not date_only_records and invalid_dates == 0,
        "note": (
            "Exact timestamps were available for all evaluated COMPLETE records."
            if not date_only_records and invalid_dates == 0 else
            "Date-only or invalid COMPLETE-record dates prevent a final timestamp-based rolling-window decision."
        ),
    }


def tenure_result(referrer, program, as_of):
    """Assess tenure only from the authorized earliest checking opening."""
    opened, _ = parse_temporal(referrer.get("first_checking_opened"))
    if opened is None:
        return None, "Earliest Rho-Bank checking-account opening date"
    required = PROGRAMS[program]["tenure_days"]
    days = (as_of.date() - opened.date()).days
    if days < required:
        return False, "Referrer tenure is below the %d-day requirement." % required
    return True, None


def assessment(request, referrer, referrals, as_of, rolling):
    program = request.get("program")
    referred = request.get("referred") if isinstance(request.get("referred"), dict) else {}
    blockers, missing = [], []
    if program not in PROGRAMS:
        return {"program": program, "eligible_for_recommendation": False,
                "blockers": ["Unsupported program; no rule set is packaged."], "missing": []}
    if not confirmed(referrer, "identity_verified"):
        blockers.append("Referrer identity has not been verified.")
    tenure_ok, tenure_issue = tenure_result(referrer, program, as_of)
    if tenure_ok is False:
        blockers.append(tenure_issue)
    elif tenure_ok is None:
        missing.append(tenure_issue)

    for field, label in (
        ("new_customer_confirmed", "Confirmation that the referred party is new to Rho-Bank"),
        ("no_closed_account_last_12_months_confirmed", "Confirmation of no Rho-Bank account closed in the prior 12 months"),
        ("different_registered_address_confirmed", "Confirmation of a different registered address"),
        ("no_other_promotion_confirmed", "Confirmation that no other new-account promotion will be used"),
    ):
        if not confirmed(referred, field):
            missing.append(label)

    if program == "Dark Green Account":
        age = referred.get("age")
        if not isinstance(age, int):
            missing.append("Referred person's age")
        elif not 17 <= age <= 26:
            blockers.append("Dark Green requires a primary holder aged 17 through 26.")
        if not confirmed(referred, "current_enrollment_verified"):
            missing.append("Current-semester enrollment verification")
    elif program == "Gold Years Account":
        age = referred.get("age")
        if not isinstance(age, int):
            missing.append("Referred person's age")
        elif age < 62:
            blockers.append("Gold Years requires age 62 or older.")
    else:
        company_age = referred.get("company_age_years")
        if not isinstance(company_age, (int, float)):
            missing.append("Company formation age")
        elif not 0 <= company_age <= 4:
            blockers.append("Sky Blue requires a company within four years of formation.")
        for field, label in (
            ("primary_signer_confirmed", "Primary authorized signer identity"),
            ("primary_signer_has_no_existing_business_confirmed", "Confirmation that the signer is not primary owner of an existing Rho-Bank business account"),
        ):
            if not confirmed(referred, field):
                missing.append(label)

    used = annual_count(referrals, program, as_of.year)
    cap = PROGRAMS[program]["annual_cap"]
    if used >= cap:
        blockers.append("Annual referral-bonus cap reached (%d of %d)." % (used, cap))
    if rolling["complete_bonus_count_observed"] >= 2:
        blockers.append("Observed completed bonuses fill the rolling nine-day cap.")
    return {
        "program": program, "annual_complete_bonus_count": used, "annual_cap": cap,
        "annual_slots_remaining": max(0, cap - used),
        "eligible_for_recommendation": not blockers and not missing and rolling["exact"],
        "blockers": blockers, "missing": missing,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"errors": ["Invalid JSON input: %s" % exc]}))
        return
    errors = []
    as_of, _ = parse_temporal(payload.get("as_of"))
    if as_of is None:
        errors.append("as_of must be a valid ISO-8601 date or datetime.")
        as_of = datetime.now(timezone.utc)
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        errors.append("referrals must be an array.")
        referrals = []
    referrer = payload.get("referrer", {})
    if not isinstance(referrer, dict):
        errors.append("referrer must be an object.")
        referrer = {}
    requests = payload.get("requests", [])
    if not isinstance(requests, list):
        errors.append("requests must be an array.")
        requests = []
    rolling = rolling_summary(referrals, as_of)
    items = [assessment(item, referrer, referrals, as_of, rolling)
             for item in requests if isinstance(item, dict)]
    print(json.dumps({"errors": errors, "rolling_window": rolling, "assessments": items}, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
