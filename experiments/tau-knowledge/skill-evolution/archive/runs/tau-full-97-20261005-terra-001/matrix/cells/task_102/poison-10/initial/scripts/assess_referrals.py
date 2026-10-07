#!/usr/bin/env python3
"""Calculate observable checking-referral caps and missing eligibility facts.

Read one JSON object from stdin and write one JSON object to stdout. This script
uses only the provided input and does not perform banking actions.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

PROGRAMS = {
    "light green": {"label": "Light Green", "annual_cap": 3, "tenure_days": 14},
    "gold years": {"label": "Gold Years", "annual_cap": 6, "tenure_days": 30},
    "sky blue": {"label": "Sky Blue", "annual_cap": 8, "tenure_days": 45},
}


def parse_datetime(value):
    """Return (aware datetime, has_time) for supported date strings."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a non-empty string")
    raw = value.strip()
    # Date-only forms deliberately receive midnight UTC solely for broad counting.
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc), False
        except ValueError:
            pass
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("unsupported date format: %s" % raw) from exc
    if parsed.tzinfo is None:
        # A timestamp without a zone is still a timestamp, but its zone is unknown.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed, True


def normalize_program(value):
    text = " ".join(str(value or "").lower().replace("account", "").split())
    if text in PROGRAMS:
        return text
    return None


def is_confirmed_true(value):
    return value is True


def candidate_assessment(candidate, tenure_days):
    if not isinstance(candidate, dict):
        return {"label": None, "program": None, "assessment": "invalid_candidate", "missing": []}
    key = normalize_program(candidate.get("program"))
    label = candidate.get("label")
    if key is None:
        return {
            "label": label,
            "program": candidate.get("program"),
            "assessment": "unsupported_program",
            "missing": [],
            "warning": "Only Light Green, Gold Years, and Sky Blue are supported by this calculator.",
        }

    missing = []
    failed = []
    program = PROGRAMS[key]
    if tenure_days is None:
        missing.append("referrer earliest-checking-account tenure")
    elif not isinstance(tenure_days, (int, float)):
        missing.append("valid numeric referrer tenure")
    elif tenure_days < program["tenure_days"]:
        failed.append("referrer tenure is below %d days" % program["tenure_days"])

    if not is_confirmed_true(candidate.get("new_customer_confirmed")):
        missing.append("confirmation that the referred party is a new Rho-Bank customer with no account or closed account in the prior 12 months")

    if key in ("light green", "gold years"):
        if not is_confirmed_true(candidate.get("different_address_confirmed")):
            missing.append("confirmation that the referred person has a different registered address")
        age = candidate.get("age")
        if not isinstance(age, (int, float)):
            missing.append("age")
        elif key == "light green" and not 13 <= age <= 24:
            failed.append("age is outside Light Green's 13–24 range")
        elif key == "gold years" and age < 62:
            failed.append("age is below Gold Years' 62-year minimum")
        elif key == "light green" and age < 18 and not is_confirmed_true(candidate.get("guardian_confirmed")):
            missing.append("guardian confirmation for a Light Green minor")
    else:
        company_age = candidate.get("company_age_years")
        if not isinstance(company_age, (int, float)):
            missing.append("company formation age")
        elif company_age > 4:
            failed.append("company is more than 4 years from formation")
        if not is_confirmed_true(candidate.get("primary_owner_no_existing_business_confirmed")):
            missing.append("confirmation that the primary authorized signer's SSN has no existing Rho-Bank business-account association")

    if failed:
        assessment = "known_requirement_not_met"
    elif missing:
        assessment = "cannot_validate"
    else:
        assessment = "known_requirements_passed_pending_account_opening_and_deposit_conditions"
    return {
        "label": label,
        "program": program["label"],
        "assessment": assessment,
        "missing": missing,
        "known_failures": failed,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of, as_of_has_time = parse_datetime(payload.get("as_of"))
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        raise ValueError("referrals must be an array")

    annual = {key: 0 for key in PROGRAMS}
    recent = []
    invalid_records = []
    date_only_in_window = not as_of_has_time
    window_start = as_of - timedelta(days=9)

    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            invalid_records.append({"index": index, "reason": "record is not an object"})
            continue
        if str(record.get("referral_status", "")).upper() != "COMPLETE":
            continue
        key = normalize_program(record.get("referred_account_type"))
        try:
            event_time, has_time = parse_datetime(record.get("date"))
        except ValueError as exc:
            invalid_records.append({"index": index, "reason": str(exc)})
            continue
        if not has_time:
            date_only_in_window = True
        if event_time.year == as_of.year and key:
            annual[key] += 1
        # Future records are not counted in a history as of the supplied time.
        if window_start <= event_time <= as_of:
            recent.append({
                "referral_id": record.get("referral_id"),
                "date": record.get("date"),
                "referred_account_type": record.get("referred_account_type"),
            })

    remaining = {
        PROGRAMS[key]["label"]: max(0, PROGRAMS[key]["annual_cap"] - annual[key])
        for key in PROGRAMS
    }
    annual_counts = {PROGRAMS[key]["label"]: annual[key] for key in PROGRAMS}
    recent_count = len(recent)
    rolling_capacity = max(0, 2 - recent_count)
    warnings = []
    if date_only_in_window:
        warnings.append(
            "The nine-day cap is timestamp-based. One or more values were date-only, so the rolling result is not exact at a nine-day boundary."
        )
    if recent_count > 2:
        warnings.append("More than two completed bonuses appear in the supplied nine-day window; additional referrals in that window are subject to automatic denial.")
    if invalid_records:
        warnings.append("Some completed records could not be included because their dates were invalid or missing.")

    tenure = payload.get("referrer_tenure_days")
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array")
    assessments = [candidate_assessment(item, tenure) for item in candidates]

    return {
        "as_of": payload.get("as_of"),
        "annual_completed_referral_bonuses": annual_counts,
        "annual_remaining_capacity": remaining,
        "annual_caps": {PROGRAMS[key]["label"]: PROGRAMS[key]["annual_cap"] for key in PROGRAMS},
        "rolling_nine_day": {
            "completed_bonus_count": recent_count,
            "remaining_bonus_capacity": rolling_capacity,
            "precision": "exact_timestamp" if not date_only_in_window else "date_only",
            "included_completed_records": recent,
        },
        "candidate_assessments": assessments,
        "invalid_records": invalid_records,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
