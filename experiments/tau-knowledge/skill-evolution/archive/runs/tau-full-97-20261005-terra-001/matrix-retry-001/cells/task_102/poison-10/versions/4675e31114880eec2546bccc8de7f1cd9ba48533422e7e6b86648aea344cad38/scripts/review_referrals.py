#!/usr/bin/env python3
"""Deterministically review read-only checking-referral screening data.

Input is one JSON object on stdin:
  now: ISO timestamp or 'YYYY-MM-DD HH:MM:SS TZ'
  referrer: {earliest_checking_opened: ISO date/timestamp}
  referrals: [{referred_account_type, referral_status, completed_at|date}]
  candidates: [{label, account_type, profile}]

A personal profile uses kind='person', age, and optional
student_currently_enrolled or student_enrollment_verified. A business profile
uses kind='business' and company_age_years. Output JSON never submits a
referral or alters a bank record.
"""
import json
import sys
from datetime import datetime, timedelta, time, timezone
from pathlib import Path

CATALOG = json.loads(
    (Path(__file__).resolve().parent.parent / "references" / "referral_programs.json").read_text(encoding="utf-8")
)


def parse_dt(value, end_of_day=False):
    """Return (datetime, date_only); accept documented tool date formats."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("timestamp is missing")
    text = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            date_value = datetime.strptime(text, fmt).date()
            return datetime.combine(date_value, time.max if end_of_day else time.min), True
        except ValueError:
            pass
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized), False
    except ValueError:
        pass
    # Tool displays may use EST/EDT. Offset is sufficient for a local screening comparison.
    for suffix, offset in ((" EST", -5), (" EDT", -4)):
        if text.endswith(suffix):
            base = datetime.strptime(text[:-len(suffix)], "%Y-%m-%d %H:%M:%S")
            return base.replace(tzinfo=timezone(timedelta(hours=offset))), False
    raise ValueError("unsupported timestamp format")


def align(value, reference):
    if reference.tzinfo is not None and value.tzinfo is None:
        return value.replace(tzinfo=reference.tzinfo)
    if reference.tzinfo is None and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def product_fit(name, profile):
    programs = CATALOG["programs"]
    if name not in programs:
        return {"status": "unknown", "reasons": ["Unsupported account type; no product rule is available."], "established_conditions": []}
    program = programs[name]
    requirements = program.get("product_requirements", {})
    kind = profile.get("kind")
    established, reasons, conditions = [], [], []
    if kind and kind != program["kind"]:
        return {"status": "ineligible", "reasons": ["Candidate type does not match this program."], "established_conditions": []}

    if program["kind"] == "personal":
        age = profile.get("age")
        if not isinstance(age, (int, float)):
            return {"status": "unknown", "reasons": ["Candidate age is required."], "established_conditions": []}
        minimum = requirements.get("minimum_age", 0)
        maximum = requirements.get("maximum_age")
        if age < minimum:
            reasons.append("Candidate is below the product minimum age.")
        else:
            established.append("Supplied age satisfies the product minimum age.")
        if maximum is not None:
            if age > maximum:
                reasons.append("Candidate exceeds the product maximum age.")
            else:
                established.append("Supplied age is within the product maximum age.")
        referral_minimum = CATALOG["general"]["minimum_referred_person_age"]
        if age < referral_minimum:
            reasons.append("A referred person must be at least 18 for this program.")
        else:
            established.append("Supplied age satisfies the general referred-person age requirement.")
        if requirements.get("current_student_enrollment_verification"):
            if profile.get("student_enrollment_verified") is True:
                established.append("Current-semester enrollment has been verified.")
            elif profile.get("student_currently_enrolled") is True:
                established.append("Supplied information states that the candidate is currently enrolled.")
                conditions.append("Acceptable current-semester enrollment documentation must be verified.")
            else:
                return {"status": "unknown", "reasons": ["Current student enrollment and semester verification are required."], "established_conditions": established}
    else:
        company_age = profile.get("company_age_years")
        if "maximum_company_age_years" in requirements:
            if not isinstance(company_age, (int, float)):
                return {"status": "unknown", "reasons": ["Company formation age is required."], "established_conditions": established}
            if company_age > requirements["maximum_company_age_years"]:
                reasons.append("Company exceeds the maximum formation age for this product.")
            else:
                established.append("Supplied company age is within the maximum formation age.")
    if reasons:
        return {"status": "ineligible", "reasons": reasons, "established_conditions": established}
    if conditions:
        return {"status": "conditional", "reasons": conditions, "established_conditions": established}
    return {"status": "eligible", "reasons": [], "established_conditions": established}


def main(data):
    try:
        now, _ = parse_dt(data.get("now"))
    except Exception as exc:
        return {"errors": ["Invalid now timestamp: %s" % exc], "screening_complete": False}
    errors = []
    referrer = data.get("referrer") if isinstance(data.get("referrer"), dict) else {}
    earliest = None
    if referrer.get("earliest_checking_opened"):
        try:
            earliest, _ = parse_dt(referrer["earliest_checking_opened"])
            earliest = align(earliest, now)
            if earliest > now:
                errors.append("earliest_checking_opened cannot be in the future.")
        except Exception as exc:
            errors.append("Invalid earliest_checking_opened: %s" % exc)
    else:
        errors.append("Missing referrer.earliest_checking_opened; referrer tenure cannot be established.")

    referrals = data.get("referrals", [])
    candidates = data.get("candidates", [])
    if not isinstance(referrals, list):
        errors.append("referrals must be an array.")
        referrals = []
    if not isinstance(candidates, list):
        errors.append("candidates must be an array.")
        candidates = []

    programs = CATALOG["programs"]
    counts = {name: 0 for name in programs}
    cutoff = now - timedelta(days=CATALOG["general"]["rolling_days"])
    recent, uncertain = 0, []
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict) or referral.get("referral_status") != "COMPLETE":
            continue
        raw_date = referral.get("completed_at", referral.get("date"))
        if not raw_date:
            errors.append("COMPLETE referral at index %d lacks completed_at/date." % index)
            continue
        try:
            low, _ = parse_dt(raw_date)
            high, _ = parse_dt(raw_date, end_of_day=True)
            low, high = align(low, now), align(high, now)
        except Exception as exc:
            errors.append("Invalid COMPLETE referral timestamp at index %d: %s" % (index, exc))
            continue
        account_type = referral.get("referred_account_type")
        if low.year == now.year and account_type in counts:
            counts[account_type] += 1
        if low >= cutoff:
            recent += 1
        elif high > cutoff:
            uncertain.append({"index": index, "account_type": account_type, "reported_date": raw_date})

    cap = CATALOG["general"]["rolling_bonus_cap"]
    rolling_status = "indeterminate" if uncertain else ("full" if recent >= cap else "available")
    rolling = {
        "status": rolling_status,
        "cutoff": cutoff.isoformat(),
        "definitely_counted_complete_bonuses": recent,
        "maximum_bonuses": cap,
        "definitely_remaining": max(0, cap - recent),
        "uncertain_cutoff_records": uncertain
    }

    results = []
    for candidate in candidates:
        candidate = candidate if isinstance(candidate, dict) else {}
        name = candidate.get("account_type")
        profile = candidate.get("profile") if isinstance(candidate.get("profile"), dict) else {}
        output = {"label": candidate.get("label"), "account_type": name, "product_fit": product_fit(name, profile)}
        if name not in programs:
            output.update({"referrer_target_status": "unknown", "referral_recommendation_permitted": False, "reasons": ["No supported referral-program rule is available for this account type."]})
            results.append(output)
            continue
        program = programs[name]
        reasons = []
        tenure_days = None
        if earliest is None or earliest > now:
            reasons.append("Referrer checking tenure has not been established.")
        else:
            tenure_days = (now - earliest).total_seconds() / 86400.0
            if tenure_days < program["referrer_tenure_days"]:
                reasons.append("Referrer does not yet meet the program tenure threshold.")
        used, annual_cap = counts[name], program.get("annual_cap")
        if annual_cap is not None and used >= annual_cap:
            reasons.append("The program's annual referral-bonus cap is exhausted.")
        if rolling_status == "full":
            reasons.append("The shared rolling nine-day referral-bonus limit is full.")
        elif rolling_status == "indeterminate":
            reasons.append("Exact timestamp is needed to resolve the rolling nine-day limit.")
        pending = [
            "Confirm referred party is a new Rho-Bank customer with no open or closed account in the prior 12 months.",
            "Confirm referrer and referred party have different registered addresses.",
            "Confirm qualifying deposit is new money rather than a Rho-Bank transfer.",
            "Confirm accounts remain in good standing and do not combine a referral code with another new-account promotion."
        ]
        if program["kind"] == "business":
            pending.append("Confirm the referred business has a different primary owner, based on the primary authorized signer's SSN, than every existing Rho-Bank business account.")
        output.update({
            "referrer_target_status": "eligible" if not reasons else "blocked",
            "referral_recommendation_permitted": not reasons,
            "referrer_tenure_days": tenure_days,
            "required_tenure_days": program["referrer_tenure_days"],
            "annual_complete_referrals": used,
            "annual_cap": annual_cap,
            "annual_remaining": None if annual_cap is None else max(0, annual_cap - used),
            "reasons": reasons,
            "pending_general_referral_checks": pending
        })
        results.append(output)

    return {
        "errors": errors,
        "screening_complete": not errors,
        "now": now.isoformat(),
        "rolling_window": rolling,
        "annual_complete_referrals_by_supported_program": counts,
        "candidates": results,
        "operational_disclosure": "I cannot create or submit a referral, and no account has been opened.",
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
