#!/usr/bin/env python3
"""Deterministically evaluate checking-referral program candidates.

Reads one JSON object on stdin and writes one JSON object on stdout.  This is
read-only decision support: it neither accesses bank data nor takes actions.
"""

import json
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


def fail(message: str) -> None:
    print(json.dumps({"error": message}, separators=(",", ":")))
    raise SystemExit(2)


def iso_datetime(value: Any, field: str) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str):
        fail(f"{field} must be an ISO-8601 timestamp or null")
    # A bare date lacks the time and timezone needed for an exact rolling check.
    if "T" not in value:
        fail(f"{field} must include time and timezone; date-only values are not exact")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail(f"{field} is not a valid ISO-8601 timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        fail(f"{field} must include a timezone offset")
    return parsed


def require_number(value: Any, field: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{field} must be numeric")
    if value < minimum:
        fail(f"{field} must be at least {minimum}")
    return float(value)


def validate_program(raw: Any, index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        fail(f"programs[{index}] must be an object")
    name = raw.get("account_type")
    if not isinstance(name, str) or not name.strip():
        fail(f"programs[{index}].account_type must be a nonempty string")
    p = dict(raw)
    p["account_type"] = name.strip()
    for field in ("referrer_bonus", "referred_bonus", "annual_cap", "qualifying_deposit", "deposit_window_days"):
        p[field] = require_number(p.get(field), f"programs[{index}].{field}")
    p["referrer_tenure_days"] = require_number(
        p.get("referrer_tenure_days"), f"programs[{index}].referrer_tenure_days", 1
    )
    minimum = p.get("candidate_age_min", 18)
    p["candidate_age_min"] = require_number(minimum, f"programs[{index}].candidate_age_min", 0)
    maximum = p.get("candidate_age_max")
    if maximum is not None:
        p["candidate_age_max"] = require_number(maximum, f"programs[{index}].candidate_age_max", 0)
        if p["candidate_age_max"] < p["candidate_age_min"]:
            fail(f"programs[{index}] has candidate_age_max below candidate_age_min")
    guardian = p.get("guardian_required_under_18", False)
    if not isinstance(guardian, bool):
        fail(f"programs[{index}].guardian_required_under_18 must be boolean")
    p["guardian_required_under_18"] = guardian
    return p


def tri(value: Any, field: str) -> Optional[bool]:
    if value is None:
        return None
    if not isinstance(value, bool):
        fail(f"candidate.{field} must be true, false, or null")
    return value


def referral_completion(raw: Dict[str, Any], index: int) -> Tuple[Optional[datetime], bool]:
    """Return exact completion timestamp and whether a date-only value was supplied."""
    value = raw.get("completed_at", raw.get("date"))
    if value is None:
        return None, False
    if not isinstance(value, str):
        fail(f"referrals[{index}] completion timestamp must be a string or null")
    if "T" not in value:
        return None, True
    return iso_datetime(value, f"referrals[{index}].completed_at"), False


def state_for_bool(value: Optional[bool], false_code: str, unknown_code: str, reasons: List[str]) -> None:
    if value is False:
        reasons.append(false_code)
    elif value is None:
        reasons.append(unknown_code)


def classify(reasons: List[str]) -> str:
    if not reasons:
        return "confirmed"
    if any(not code.endswith("_UNKNOWN") for code in reasons):
        return "ineligible"
    return "conditional"


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        fail("input must be a JSON object")
    now = iso_datetime(payload.get("now"), "now")
    if now is None:
        fail("now is required")
    raw_programs = payload.get("programs")
    if not isinstance(raw_programs, list):
        fail("programs must be an array")
    programs = [validate_program(item, i) for i, item in enumerate(raw_programs)]
    if len({p["account_type"] for p in programs}) != len(programs):
        fail("program account_type values must be unique")

    referrer = payload.get("referrer")
    candidate = payload.get("candidate")
    referrals = payload.get("referrals", [])
    if not isinstance(referrer, dict) or not isinstance(candidate, dict) or not isinstance(referrals, list):
        fail("referrer and candidate must be objects and referrals must be an array")
    first_opened = iso_datetime(referrer.get("first_checking_opened_at"), "referrer.first_checking_opened_at")
    if first_opened is not None and first_opened > now:
        fail("referrer.first_checking_opened_at cannot be in the future")

    new_customer = tri(candidate.get("is_new_customer"), "is_new_customer")
    different_address = tri(candidate.get("different_registered_address"), "different_registered_address")
    guardian_confirmed = tri(candidate.get("guardian_confirmed"), "guardian_confirmed")
    new_money = tri(candidate.get("planned_deposit_is_new_money"), "planned_deposit_is_new_money")
    within_window = tri(candidate.get("planned_deposit_within_window"), "planned_deposit_within_window")
    age = candidate.get("age")
    if age is not None:
        age = require_number(age, "candidate.age", 0)
    deposit = candidate.get("planned_deposit_amount")
    if deposit is not None:
        deposit = require_number(deposit, "candidate.planned_deposit_amount", 0)

    completed: List[Tuple[Dict[str, Any], Optional[datetime], bool]] = []
    for i, item in enumerate(referrals):
        if not isinstance(item, dict):
            fail(f"referrals[{i}] must be an object")
        if item.get("referral_status") == "COMPLETE":
            timestamp, date_only = referral_completion(item, i)
            completed.append((item, timestamp, date_only))

    cutoff = now - timedelta(days=9)
    in_window_exact: List[datetime] = []
    rolling_unknown = False
    for _, timestamp, date_only in completed:
        if date_only or timestamp is None:
            rolling_unknown = True
        elif cutoff <= timestamp <= now:
            in_window_exact.append(timestamp)
    if rolling_unknown:
        rolling_state = "unknown"
    elif len(in_window_exact) >= 2:
        rolling_state = "blocked"
    else:
        rolling_state = "available"

    results: List[Dict[str, Any]] = []
    for p in programs:
        reasons: List[str] = []
        state_for_bool(new_customer, "NOT_NEW_CUSTOMER", "NEW_CUSTOMER_UNKNOWN", reasons)
        state_for_bool(different_address, "SAME_REGISTERED_ADDRESS", "REGISTERED_ADDRESS_DIFFERENCE_UNKNOWN", reasons)
        state_for_bool(new_money, "DEPOSIT_NOT_NEW_MONEY", "DEPOSIT_SOURCE_UNKNOWN", reasons)
        state_for_bool(within_window, "DEPOSIT_NOT_WITHIN_WINDOW", "DEPOSIT_TIMING_UNKNOWN", reasons)

        if first_opened is None:
            reasons.append("REFERRER_TENURE_UNKNOWN")
        elif first_opened + timedelta(days=p["referrer_tenure_days"]) > now:
            reasons.append("REFERRER_TENURE_NOT_MET")

        if rolling_state == "unknown":
            reasons.append("ROLLING_WINDOW_UNKNOWN")
        elif rolling_state == "blocked":
            reasons.append("ROLLING_WINDOW_CAP_REACHED")

        annual_count = 0
        annual_unknown = False
        for referral, stamp, date_only in completed:
            if referral.get("referred_account_type") != p["account_type"]:
                continue
            if date_only or stamp is None:
                annual_unknown = True
            elif stamp.year == now.year:
                annual_count += 1
        if annual_unknown:
            reasons.append("ANNUAL_CAP_UNKNOWN")
        elif annual_count >= p["annual_cap"]:
            reasons.append("ANNUAL_CAP_REACHED")

        if deposit is None:
            reasons.append("DEPOSIT_AMOUNT_UNKNOWN")
        elif deposit < p["qualifying_deposit"]:
            reasons.append("DEPOSIT_AMOUNT_TOO_LOW")

        if age is None:
            reasons.append("CANDIDATE_AGE_UNKNOWN")
        else:
            if age < p["candidate_age_min"]:
                reasons.append("CANDIDATE_TOO_YOUNG")
            if p["candidate_age_max"] is not None and age > p["candidate_age_max"]:
                reasons.append("CANDIDATE_TOO_OLD")
            if age < 18 and p["guardian_required_under_18"]:
                state_for_bool(guardian_confirmed, "GUARDIAN_REQUIREMENT_NOT_MET", "GUARDIAN_REQUIREMENT_UNKNOWN", reasons)

        result = {
            "account_type": p["account_type"],
            "referrer_bonus": p["referrer_bonus"],
            "referred_bonus": p["referred_bonus"],
            "combined_bonus": p["referrer_bonus"] + p["referred_bonus"],
            "qualifying_deposit": p["qualifying_deposit"],
            "deposit_window_days": p["deposit_window_days"],
            "annual_completed_count": annual_count,
            "eligibility": classify(reasons),
            "reason_codes": reasons,
        }
        results.append(result)

    confirmed = sorted((r for r in results if r["eligibility"] == "confirmed"), key=lambda r: (-r["combined_bonus"], r["account_type"]))
    conditional = sorted((r for r in results if r["eligibility"] == "conditional"), key=lambda r: (-r["combined_bonus"], r["account_type"]))
    ineligible = sorted((r for r in results if r["eligibility"] == "ineligible"), key=lambda r: (-r["combined_bonus"], r["account_type"]))
    return {
        "rolling_window": {
            "state": rolling_state,
            "completed_bonus_count_in_window": len(in_window_exact),
            "window_start": cutoff.isoformat(),
            "now": now.isoformat(),
            "in_window_completion_timestamps": [stamp.isoformat() for stamp in sorted(in_window_exact)],
            "timestamp_precision_problem": rolling_unknown,
        },
        "confirmed_ranked_options": confirmed,
        "conditional_options": conditional,
        "ineligible_options": ineligible,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":"), sort_keys=True))
    except BrokenPipeError:
        pass
    except SystemExit:
        raise
    except Exception as exc:  # Keep stdout JSON for callers even on unexpected malformed input.
        print(json.dumps({"error": f"unexpected evaluation error: {exc}"}, separators=(",", ":")))
        raise SystemExit(2)
