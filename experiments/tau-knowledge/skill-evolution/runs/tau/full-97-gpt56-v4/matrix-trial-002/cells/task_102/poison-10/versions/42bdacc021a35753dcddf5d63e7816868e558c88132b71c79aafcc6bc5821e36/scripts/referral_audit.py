#!/usr/bin/env python3
"""Audit stated referral facts. Reads JSON stdin and writes JSON stdout."""
import json
import sys
from datetime import datetime, date, timedelta, timezone

PROGRAMS = {
    "Dark Green Account": {"tenure_days": 45, "annual_cap": 6},
    "Gold Years Account": {"tenure_days": 30, "annual_cap": 6},
    "Sky Blue Account": {"tenure_days": 45, "annual_cap": 8},
}


def parse_temporal(value):
    if not isinstance(value, str) or not value.strip():
        return None, False
    text = value.strip()
    try:
        if "T" in text or " " in text:
            normalized = text.replace("Z", "+00:00")
            moment = datetime.fromisoformat(normalized)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            return moment.astimezone(timezone.utc), True
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc), False
    except ValueError:
        for fmt in ("%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc), False
            except ValueError:
                pass
    return None, False


def confirmed(data, key):
    return data.get(key) is True


def annual_count(referrals, program, year):
    count = 0
    for item in referrals:
        when, _ = parse_temporal(item.get("date"))
        if (item.get("referred_account_type") == program and
                item.get("referral_status") == "COMPLETE" and when and when.year == year):
            count += 1
    return count


def rolling_summary(referrals, as_of):
    window_start = as_of - timedelta(days=9)
    complete = []
    date_only_records = []
    for item in referrals:
        if item.get("referral_status") != "COMPLETE":
            continue
        when, has_time = parse_temporal(item.get("date"))
        if not when:
            continue
        if has_time:
            if window_start <= when <= as_of:
                complete.append(item)
        else:
            # Date-only records cannot resolve an exact timestamp boundary.
            if window_start.date() <= when.date() <= as_of.date():
                date_only_records.append(item)
    exact = not date_only_records
    count = len(complete) + len(date_only_records)
    return {
        "window_start": window_start.isoformat(),
        "as_of": as_of.isoformat(),
        "complete_bonus_count_observed": count,
        "slots_if_observed_count_is_final": max(0, 2 - count),
        "exact": exact,
        "note": ("Exact timestamps were available for relevant records." if exact else
                 "One or more relevant COMPLETE records have date-only values; obtain authoritative timestamps before final rolling-window approval."),
    }


def item_assessment(request, referrer, referrals, as_of, rolling):
    program = request.get("program")
    referred = request.get("referred") if isinstance(request.get("referred"), dict) else {}
    blockers, missing = [], []
    if program not in PROGRAMS:
        return {"program": program, "eligible_for_recommendation": False,
                "blockers": ["Unsupported program; no rule set is packaged."], "missing": []}

    if not confirmed(referrer, "identity_verified"):
        blockers.append("Referrer identity has not been verified.")
    opened, _ = parse_temporal(referrer.get("first_checking_opened"))
    if not opened:
        missing.append("Earliest Rho-Bank checking-account opening date")
    else:
        tenure = (as_of.date() - opened.date()).days
        if tenure < PROGRAMS[program]["tenure_days"]:
            blockers.append("Referrer tenure is below the %d-day requirement." % PROGRAMS[program]["tenure_days"])

    universal = [
        ("new_customer_confirmed", "Confirmation that the referred party is new to Rho-Bank"),
        ("no_closed_account_last_12_months_confirmed", "Confirmation of no Rho-Bank account closed in the prior 12 months"),
        ("different_registered_address_confirmed", "Confirmation of a different registered address"),
        ("no_other_promotion_confirmed", "Confirmation that no other new-account promotion will be used"),
    ]
    for field, label in universal:
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
        elif company_age > 4:
            blockers.append("Sky Blue requires a company within four years of formation.")
        for field, label in [
            ("primary_signer_confirmed", "Primary authorized signer identity"),
            ("primary_signer_has_no_existing_business_confirmed", "Confirmation that the signer is not primary owner of an existing Rho-Bank business account"),
        ]:
            if not confirmed(referred, field):
                missing.append(label)

    used = annual_count(referrals, program, as_of.year)
    cap = PROGRAMS[program]["annual_cap"]
    if used >= cap:
        blockers.append("Annual referral-bonus cap reached (%d of %d)." % (used, cap))
    if rolling["complete_bonus_count_observed"] >= 2:
        blockers.append("Observed completed bonuses fill the rolling nine-day cap.")

    return {
        "program": program,
        "annual_complete_bonus_count": used,
        "annual_cap": cap,
        "annual_slots_remaining": max(0, cap - used),
        "eligible_for_recommendation": not blockers and not missing and rolling["exact"],
        "blockers": blockers,
        "missing": missing,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"errors": ["Invalid JSON input: %s" % exc]}))
        return
    errors = []
    as_of, _ = parse_temporal(payload.get("as_of"))
    if not as_of:
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
    items = [item_assessment(r, referrer, referrals, as_of, rolling)
             for r in requests if isinstance(r, dict)]
    print(json.dumps({"errors": errors, "rolling_window": rolling, "assessments": items}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
