#!/usr/bin/env python3
"""Review checking-referral screening data.

Input JSON:
  now: ISO-8601 timestamp (timezone recommended)
  referrer: {earliest_checking_opened: ISO date/timestamp}
  referrals: [{referred_account_type, referral_status, completed_at|date}]
  candidates: [{label, account_type, profile}]

Profiles use kind "person" with age and optional student_enrollment_verified,
or kind "business" with company_age_years. The output does not submit or alter
any bank record.
"""
import json
import sys
from datetime import datetime, timedelta, time
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parent.parent / "references" / "referral_programs.json").read_text())


def parse_dt(value, end_of_day=False):
    """Return (datetime, date_only). Raises ValueError for invalid values."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")
    text = value.strip()
    date_only = len(text) == 10 and text[4] == "-" and text[7] == "-"
    if date_only:
        d = datetime.strptime(text, "%Y-%m-%d").date()
        return datetime.combine(d, time.max if end_of_day else time.min), True
    return datetime.fromisoformat(text.replace("Z", "+00:00")), False


def align(dt, reference):
    """Apply reference tzinfo to a date-only/naive timestamp for comparison."""
    if reference.tzinfo is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=reference.tzinfo)
    if reference.tzinfo is None and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def days_since(start, now):
    start = align(start, now)
    return (now - start).total_seconds() / 86400.0


def product_fit(program_name, profile):
    programs = CATALOG["programs"]
    if program_name not in programs:
        return {"status": "unknown", "reasons": ["Unsupported account type; no product rule is available."]}
    program = programs[program_name]
    req = program.get("product_requirements", {})
    kind = profile.get("kind")
    reasons = []
    conditional = []
    if kind and kind != program["kind"]:
        return {"status": "ineligible", "reasons": ["Candidate type does not match this program."]}
    if program["kind"] == "personal":
        age = profile.get("age")
        if not isinstance(age, (int, float)):
            return {"status": "unknown", "reasons": ["Candidate age is required."]}
        if age < req.get("minimum_age", 0):
            reasons.append("Candidate is below the product minimum age.")
        if "maximum_age" in req and age > req["maximum_age"]:
            reasons.append("Candidate exceeds the product maximum age.")
        # The universal referral restriction is stricter than a product that admits a 17-year-old.
        if age < CATALOG["general"]["minimum_referred_person_age"]:
            reasons.append("A referred person must be at least 18 for this program.")
        if req.get("current_student_enrollment_verification"):
            if profile.get("student_enrollment_verified") is True:
                pass
            elif profile.get("student_currently_enrolled") is True:
                conditional.append("Current enrollment must be verified for the active semester.")
            else:
                return {"status": "unknown", "reasons": ["Current student enrollment and semester verification are required."]}
    else:
        age = profile.get("company_age_years")
        if "maximum_company_age_years" in req:
            if not isinstance(age, (int, float)):
                return {"status": "unknown", "reasons": ["Company formation age is required."]}
            if age > req["maximum_company_age_years"]:
                reasons.append("Company exceeds the maximum formation age for this product.")
    if reasons:
        return {"status": "ineligible", "reasons": reasons}
    if conditional:
        return {"status": "conditional", "reasons": conditional}
    return {"status": "eligible", "reasons": []}


def main(data):
    errors = []
    try:
        now, _ = parse_dt(data.get("now"))
    except Exception as exc:
        return {"errors": ["Invalid now timestamp: %s" % exc], "screening_complete": False}

    referrer = data.get("referrer") if isinstance(data.get("referrer"), dict) else {}
    opened_value = referrer.get("earliest_checking_opened")
    earliest = None
    if opened_value:
        try:
            earliest, _ = parse_dt(opened_value)
            earliest = align(earliest, now)
            if earliest > now:
                errors.append("earliest_checking_opened cannot be in the future.")
        except Exception as exc:
            errors.append("Invalid earliest_checking_opened: %s" % exc)
    else:
        errors.append("Missing referrer.earliest_checking_opened; referrer tenure cannot be established.")

    referrals = data.get("referrals", [])
    if not isinstance(referrals, list):
        errors.append("referrals must be an array.")
        referrals = []
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        errors.append("candidates must be an array.")
        candidates = []

    programs = CATALOG["programs"]
    year_counts = {name: 0 for name in programs}
    cutoff = now - timedelta(days=CATALOG["general"]["rolling_days"])
    definitely_recent = 0
    uncertain_cutoff_records = []

    for idx, referral in enumerate(referrals):
        if not isinstance(referral, dict) or referral.get("referral_status") != "COMPLETE":
            continue
        account_type = referral.get("referred_account_type")
        raw_date = referral.get("completed_at", referral.get("date"))
        if not raw_date:
            errors.append("COMPLETE referral at index %d lacks completed_at/date." % idx)
            continue
        try:
            low, date_only = parse_dt(raw_date, False)
            high, _ = parse_dt(raw_date, True)
            low, high = align(low, now), align(high, now)
        except Exception as exc:
            errors.append("Invalid COMPLETE referral timestamp at index %d: %s" % (idx, exc))
            continue
        if low.year == now.year and account_type in year_counts:
            year_counts[account_type] += 1
        # A date-only record straddling the cutoff is not silently classified.
        if low >= cutoff:
            definitely_recent += 1
        elif high > cutoff:
            uncertain_cutoff_records.append({"index": idx, "account_type": account_type, "reported_date": raw_date})

    if uncertain_cutoff_records:
        rolling_status = "indeterminate"
    elif definitely_recent >= CATALOG["general"]["rolling_bonus_cap"]:
        rolling_status = "full"
    else:
        rolling_status = "available"
    rolling = {
        "status": rolling_status,
        "cutoff": cutoff.isoformat(),
        "definitely_counted_complete_bonuses": definitely_recent,
        "maximum_bonuses": CATALOG["general"]["rolling_bonus_cap"],
        "definitely_remaining": max(0, CATALOG["general"]["rolling_bonus_cap"] - definitely_recent),
        "uncertain_cutoff_records": uncertain_cutoff_records
    }

    results = []
    for candidate in candidates:
        candidate = candidate if isinstance(candidate, dict) else {}
        name = candidate.get("account_type")
        profile = candidate.get("profile") if isinstance(candidate.get("profile"), dict) else {}
        output = {"label": candidate.get("label"), "account_type": name}
        if name not in programs:
            output.update({
                "referrer_target_status": "unknown",
                "referral_recommendation_permitted": False,
                "product_fit": product_fit(name, profile),
                "reasons": ["No supported referral-program rule is available for this account type."]
            })
            results.append(output)
            continue
        program = programs[name]
        reasons = []
        tenure_days = None
        if earliest is None or earliest > now:
            reasons.append("Referrer checking tenure has not been established.")
        else:
            tenure_days = days_since(earliest, now)
            if tenure_days < program["referrer_tenure_days"]:
                reasons.append("Referrer does not yet meet the program tenure threshold.")
        used = year_counts[name]
        cap = program.get("annual_cap")
        if cap is not None and used >= cap:
            reasons.append("The program's annual referral-bonus cap is exhausted.")
        if rolling_status == "full":
            reasons.append("The shared rolling nine-day referral-bonus limit is full.")
        elif rolling_status == "indeterminate":
            reasons.append("Exact timestamp is needed to resolve the rolling nine-day limit.")
        status = "eligible" if not reasons else "blocked"
        output.update({
            "referrer_target_status": status,
            "referral_recommendation_permitted": status == "eligible",
            "referrer_tenure_days": tenure_days,
            "required_tenure_days": program["referrer_tenure_days"],
            "annual_complete_referrals": used,
            "annual_cap": cap,
            "annual_remaining": None if cap is None else max(0, cap - used),
            "product_fit": product_fit(name, profile),
            "reasons": reasons,
            "pending_general_referral_checks": [
                "Confirm referred party is a new Rho-Bank customer with no open or closed account in the prior 12 months.",
                "Confirm referrer and referred party have different registered addresses.",
                "Confirm qualifying deposit is new money rather than a Rho-Bank transfer.",
                "Confirm accounts remain in good standing and do not combine a referral code with another new-account promotion."
            ]
        })
        if program["kind"] == "business":
            output["pending_general_referral_checks"].append(
                "Confirm the referred business has a different primary owner, based on the primary authorized signer's SSN, than every existing Rho-Bank business account."
            )
        results.append(output)

    return {
        "errors": errors,
        "screening_complete": not errors,
        "now": now.isoformat(),
        "rolling_window": rolling,
        "annual_complete_referrals_by_supported_program": year_counts,
        "candidates": results,
        "note": "Rolling capacity applies when successful bonuses are received; candidate results do not forecast qualification timing."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": ["Input processing failed: %s" % exc], "screening_complete": False}))
