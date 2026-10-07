#!/usr/bin/env python3
"""Assess observable referral caps and known, missing, and failed conditions.

Reads one JSON object from stdin and emits one JSON object to stdout. The script
uses supplied facts only and never performs a banking action.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

PROGRAMS = {
    "light green": {"label": "Light Green", "annual_cap": 3, "tenure_days": 14},
    "gold years": {"label": "Gold Years", "annual_cap": 6, "tenure_days": 30},
    "sky blue": {"label": "Sky Blue", "annual_cap": 8, "tenure_days": 45},
}


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a non-empty string")
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc), False
        except ValueError:
            pass
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("unsupported date format: %s" % value) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, True


def program_key(value):
    text = " ".join(str(value or "").lower().replace("account", "").split())
    return text if text in PROGRAMS else None


def confirmed(value):
    return value is True


def assess_candidate(candidate, tenure_days, remaining):
    if not isinstance(candidate, dict):
        return {"assessment": "invalid_candidate", "missing_conditions": [], "known_failures": [], "satisfied_conditions": []}
    key = program_key(candidate.get("program"))
    label = candidate.get("label")
    if key is None:
        return {
            "label": label, "program": candidate.get("program"),
            "assessment": "unsupported_program", "missing_conditions": [],
            "known_failures": [], "satisfied_conditions": [],
            "warning": "Only Light Green, Gold Years, and Sky Blue are supported.",
        }
    spec = PROGRAMS[key]
    missing, failures, satisfied = [], [], []

    if tenure_days is None:
        missing.append("referrer earliest-checking-account tenure")
    elif not isinstance(tenure_days, (int, float)):
        missing.append("valid numeric referrer tenure")
    elif tenure_days < spec["tenure_days"]:
        failures.append("referrer tenure is below %d days" % spec["tenure_days"])
    else:
        satisfied.append("referrer tenure meets the %d-day requirement" % spec["tenure_days"])

    if confirmed(candidate.get("new_customer_confirmed")):
        satisfied.append("new-customer requirement is confirmed")
    else:
        missing.append("confirmation that the referred party is new to Rho-Bank with no current or recently closed account")

    if key in ("light green", "gold years"):
        if confirmed(candidate.get("different_address_confirmed")):
            satisfied.append("different registered address is confirmed")
        else:
            missing.append("confirmation that the referred person has a different registered address")
        age = candidate.get("age")
        if not isinstance(age, (int, float)):
            missing.append("age")
        elif key == "light green" and not 13 <= age <= 24:
            failures.append("age is outside Light Green's 13–24 range")
        elif key == "gold years" and age < 62:
            failures.append("age is below Gold Years' 62-year minimum")
        else:
            satisfied.append("age meets the %s requirement" % ("13–24" if key == "light green" else "62+") )
        if key == "light green" and isinstance(age, (int, float)) and age < 18:
            if confirmed(candidate.get("guardian_confirmed")):
                satisfied.append("guardian confirmation is provided")
            else:
                missing.append("guardian confirmation for a Light Green minor")
    else:
        company_age = candidate.get("company_age_years")
        if not isinstance(company_age, (int, float)):
            missing.append("company formation age")
        elif company_age > 4:
            failures.append("company is more than 4 years from formation")
        else:
            satisfied.append("company formation age is within 4 years")
        if confirmed(candidate.get("primary_owner_no_existing_business_confirmed")):
            satisfied.append("primary authorized signer has no existing Rho-Bank business-account association")
        else:
            missing.append("confirmation that the primary authorized signer's SSN has no existing Rho-Bank business-account association")

    capacity = remaining[spec["label"]]
    if capacity == 0:
        failures.append("annual %s referral-bonus cap is reached" % spec["label"])
    if failures:
        result = "known_requirement_not_met"
    elif missing:
        result = "cannot_validate"
    else:
        result = "known_requirements_passed_pending_account_opening_and_deposit_conditions"
    return {
        "label": label, "program": spec["label"], "assessment": result,
        "annual_remaining_capacity": capacity, "satisfied_conditions": satisfied,
        "missing_conditions": missing, "known_failures": failures,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of, as_of_has_time = parse_date(payload.get("as_of"))
    referrals = payload.get("referrals", [])
    candidates = payload.get("candidates", [])
    if not isinstance(referrals, list) or not isinstance(candidates, list):
        raise ValueError("referrals and candidates must be arrays")

    counts = {key: 0 for key in PROGRAMS}
    recent, invalid = [], []
    date_only = not as_of_has_time
    start = as_of - timedelta(days=9)
    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            invalid.append({"index": index, "reason": "record is not an object"})
            continue
        if str(record.get("referral_status", "")).upper() != "COMPLETE":
            continue
        try:
            when, has_time = parse_date(record.get("date"))
        except ValueError as exc:
            invalid.append({"index": index, "reason": str(exc)})
            continue
        date_only = date_only or not has_time
        key = program_key(record.get("referred_account_type"))
        if key and when.year == as_of.year:
            counts[key] += 1
        if start <= when <= as_of:
            recent.append({"referral_id": record.get("referral_id"), "date": record.get("date"), "referred_account_type": record.get("referred_account_type")})

    completed = {PROGRAMS[key]["label"]: counts[key] for key in PROGRAMS}
    remaining = {PROGRAMS[key]["label"]: max(0, PROGRAMS[key]["annual_cap"] - counts[key]) for key in PROGRAMS}
    warnings = []
    if date_only:
        warnings.append("The rolling nine-day cap is timestamp-based; date-only input makes boundary results inexact.")
    if len(recent) > 2:
        warnings.append("More than two completed bonuses occur in the supplied nine-day window; further referrals in that window are subject to automatic denial.")
    if invalid:
        warnings.append("Some completed records were excluded because their dates were missing or invalid.")

    tenure = payload.get("referrer_tenure_days")
    return {
        "as_of": payload.get("as_of"),
        "annual_completed_referral_bonuses": completed,
        "annual_caps": {PROGRAMS[key]["label"]: PROGRAMS[key]["annual_cap"] for key in PROGRAMS},
        "annual_remaining_capacity": remaining,
        "rolling_nine_day": {
            "completed_bonus_count": len(recent),
            "remaining_bonus_capacity": max(0, 2 - len(recent)),
            "precision": "exact_timestamp" if not date_only else "date_only",
            "included_completed_records": recent,
        },
        "candidate_assessments": [assess_candidate(c, tenure, remaining) for c in candidates],
        "invalid_records": invalid, "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
