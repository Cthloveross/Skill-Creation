#!/usr/bin/env python3
"""Deterministically assess checking-referral eligibility facts.

Reads one JSON object from stdin and writes one JSON object to stdout.  It uses
only the Python standard library and does not perform banking actions.
"""

import json
import sys
from datetime import datetime, timedelta, timezone


PROGRAMS = {
    "gold_years": {
        "canonical_name": "Gold Years Account",
        "tenure_days": 30,
        "annual_cap": 6,
        "deposit_amount": 1000,
        "deposit_window_days": 90,
        "referrer_reward": 50,
        "candidate_reward": 75,
        "candidate_kind": "personal",
        "age_min": 62,
    },
    "dark_green": {
        "canonical_name": "Dark Green Account",
        "tenure_days": 45,
        "annual_cap": 6,
        "deposit_amount": 1000,
        "deposit_window_days": 60,
        "referrer_reward": 40,
        "candidate_reward": 30,
        "candidate_kind": "personal",
        "age_min": 17,
        "age_max": 26,
    },
    "sky_blue": {
        "canonical_name": "Sky Blue Account",
        "tenure_days": 45,
        "annual_cap": 8,
        "deposit_amount": 10000,
        "deposit_window_days": 90,
        "referrer_reward": 150,
        "candidate_reward": 250,
        "candidate_kind": "business",
        "formation_max_years": 4,
    },
}


def parse_time(value):
    """Parse an ISO timestamp/date into a naive UTC datetime.

    A date-only value is interpreted as midnight and should be treated as less
    precise for a rolling-window decision.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.strptime(text, "%Y-%m-%d")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def is_date_only(value):
    return isinstance(value, str) and len(value.strip()) == 10


def normalize_program(value):
    text = "".join(ch.lower() for ch in str(value or "") if ch.isalnum())
    if "goldyears" in text:
        return "gold_years"
    if "darkgreen" in text:
        return "dark_green"
    if "skyblue" in text:
        return "sky_blue"
    return None


def tri_check(value, true_message, false_message, unknown_message):
    if value is True:
        return {"status": "pass", "message": true_message}
    if value is False:
        return {"status": "fail", "message": false_message}
    return {"status": "unknown", "message": unknown_message}


def referrer_status(referrer, as_of, program):
    active = referrer.get("active_checking_in_good_standing")
    opened_raw = referrer.get("earliest_checking_opened")
    opened = parse_time(opened_raw)
    missing = []
    blockers = []

    if active is not True:
        if active is False:
            blockers.append("The checking relationship is not active and in good standing.")
        else:
            missing.append("active_checking_in_good_standing")
    if opened is None:
        missing.append("earliest_checking_opened")
    elif opened > as_of:
        blockers.append("The supplied earliest checking-opened date is after the assessment time.")
    elif (as_of - opened).days < program["tenure_days"]:
        blockers.append(
            "Checking tenure is below the required %d days." % program["tenure_days"]
        )

    if blockers:
        state = "ineligible"
    elif missing:
        state = "unknown"
    else:
        state = "eligible"
    return {"status": state, "missing": missing, "blockers": blockers}


def candidate_checks(candidate, program):
    checks = {}
    checks["new_customer"] = tri_check(
        candidate.get("new_customer_no_account_last_12_months"),
        "The candidate is confirmed new to Rho-Bank with no existing or closed account in the prior 12 months.",
        "The candidate does not meet the new-customer/no-recent-account condition.",
        "Confirm no existing Rho-Bank account and no account closed in the prior 12 months.",
    )
    checks["no_other_promotion"] = tri_check(
        candidate.get("has_other_new_account_promotion") is False if "has_other_new_account_promotion" in candidate else None,
        "No other new-account promotion is indicated.",
        "A referral bonus cannot be combined with another new-account promotion or sign-up bonus.",
        "Confirm whether another new-account promotion or sign-up bonus will be applied.",
    )
    checks["one_referral_code"] = tri_check(
        candidate.get("one_referral_code_only"),
        "One referral code will be used.",
        "Only one referral code can be applied per new account.",
        "Confirm that only one referral code will be applied.",
    )

    if program["candidate_kind"] == "personal":
        checks["different_address"] = tri_check(
            candidate.get("different_registered_address"),
            "The registered address differs from the referrer's address.",
            "The referrer and referred customer cannot be registered at the same address.",
            "Confirm that the candidate's registered address differs from the referrer's address.",
        )
        age = candidate.get("age")
        if not isinstance(age, (int, float)) or isinstance(age, bool):
            checks["age"] = {"status": "unknown", "message": "Confirm the candidate's age."}
        elif age < program["age_min"] or ("age_max" in program and age > program["age_max"]):
            if "age_max" in program:
                msg = "Candidate age must be between %d and %d for this program." % (program["age_min"], program["age_max"])
            else:
                msg = "Candidate must be at least %d for this program." % program["age_min"]
            checks["age"] = {"status": "fail", "message": msg}
        else:
            checks["age"] = {"status": "pass", "message": "Candidate meets the program age range."}
    else:
        checks["distinct_business_primary_owner"] = tri_check(
            candidate.get("primary_owner_no_existing_rho_business_account"),
            "The business has a distinct qualifying primary owner.",
            "The business primary owner conflicts with an existing Rho-Bank business account.",
            "Confirm that the primary authorized signer/owner does not already own a Rho-Bank business account.",
        )
        age = candidate.get("formation_age_years")
        if not isinstance(age, (int, float)) or isinstance(age, bool):
            checks["formation_age"] = {"status": "unknown", "message": "Confirm business age from formation documents."}
        elif age > program["formation_max_years"] or age < 0:
            checks["formation_age"] = {"status": "fail", "message": "Sky Blue requires a business within 4 years of formation."}
        else:
            checks["formation_age"] = {"status": "pass", "message": "Business is within 4 years of formation."}

    return checks


def main(data):
    as_of = parse_time(data.get("as_of"))
    if as_of is None:
        return {"error": "Invalid or missing as_of. Supply an ISO-8601 timestamp or YYYY-MM-DD."}

    warnings = []
    referrals = data.get("referrals", [])
    if not isinstance(referrals, list):
        return {"error": "referrals must be a JSON array."}
    referrer = data.get("referrer") or {}
    if not isinstance(referrer, dict):
        return {"error": "referrer must be a JSON object."}

    complete = []
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            warnings.append("Ignored non-object referral at index %d." % index)
            continue
        if str(referral.get("referral_status", "")).upper() != "COMPLETE":
            continue
        stamp_value = referral.get("timestamp", referral.get("date"))
        stamp = parse_time(stamp_value)
        if stamp is None:
            warnings.append("Ignored COMPLETE referral at index %d because its date is invalid or missing." % index)
            continue
        if is_date_only(stamp_value):
            warnings.append("COMPLETE referral at index %d has a date but no timestamp; rolling-window precision may be limited." % index)
        complete.append({"time": stamp, "program": normalize_program(referral.get("referred_account_type"))})

    rolling_start = as_of - timedelta(days=9)
    recent = [r for r in complete if rolling_start <= r["time"] <= as_of]
    rolling_count = len(recent)
    if rolling_count >= 2:
        rolling_status = "at_limit"
    else:
        rolling_status = "capacity_available"

    program_results = {}
    requested_programs = set()
    candidates = data.get("candidates", [])
    if not isinstance(candidates, list):
        return {"error": "candidates must be a JSON array."}
    for candidate in candidates:
        if isinstance(candidate, dict):
            code = normalize_program(candidate.get("account_type"))
            if code:
                requested_programs.add(code)
    for code in requested_programs:
        program = PROGRAMS[code]
        annual = sum(1 for r in complete if r["program"] == code and r["time"].year == as_of.year)
        eligibility = referrer_status(referrer, as_of, program)
        if annual >= program["annual_cap"]:
            eligibility["annual_cap_blocker"] = "The %s annual referral-bonus cap has been reached." % program["canonical_name"]
            eligibility["status"] = "ineligible"
        else:
            eligibility["annual_cap_blocker"] = None
        program_results[code] = {
            "program": program["canonical_name"],
            "annual_complete_bonuses": annual,
            "annual_cap": program["annual_cap"],
            "annual_capacity": max(0, program["annual_cap"] - annual),
            "referrer": eligibility,
            "qualification": {
                "deposit_amount": program["deposit_amount"],
                "deposit_within_days_of_opening": program["deposit_window_days"],
                "referrer_tenure_days": program["tenure_days"],
                "referrer_reward": program["referrer_reward"],
                "candidate_reward": program["candidate_reward"],
            },
        }

    candidate_results = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            candidate_results.append({"index": index, "status": "unsupported", "message": "Candidate must be a JSON object."})
            continue
        code = normalize_program(candidate.get("account_type"))
        if code is None:
            candidate_results.append({
                "index": index,
                "label": candidate.get("label"),
                "status": "unsupported",
                "message": "Only Gold Years, Dark Green, and Sky Blue are supported by this packaged policy.",
            })
            continue
        checks = candidate_checks(candidate, PROGRAMS[code])
        states = [item["status"] for item in checks.values()]
        status = "fail" if "fail" in states else ("unknown" if "unknown" in states else "pass")
        candidate_results.append({
            "index": index,
            "label": candidate.get("label"),
            "program": PROGRAMS[code]["canonical_name"],
            "status": status,
            "checks": checks,
            "ongoing_conditions": [
                "Qualifying deposit must be new money, not a transfer from another Rho-Bank account.",
                "Qualifying deposit must remain in the account for at least 30 days after the qualifying period ends.",
                "Both accounts must remain in good standing; closure within 90 days may reverse the bonus.",
            ],
        })

    gate_complete = bool(requested_programs) and all(
        result["referrer"]["status"] in ("eligible", "ineligible") for result in program_results.values()
    )
    return {
        "as_of": data.get("as_of"),
        "referrer_gate_complete": gate_complete,
        "rolling_window": {
            "window_start": rolling_start.isoformat(),
            "completed_bonus_count_all_account_types": rolling_count,
            "maximum": 2,
            "current_capacity": max(0, 2 - rolling_count),
            "status": rolling_status,
            "note": "This is current bonus capacity, not a reservation or promise for a referral submitted now.",
        },
        "programs": program_results,
        "candidates": candidate_results,
        "data_warnings": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON value must be an object.")
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
