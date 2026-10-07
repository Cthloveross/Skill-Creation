#!/usr/bin/env python3
"""Evaluate supplied personal-checking eligibility facts without bank-side actions.

Input: one JSON object as documented in SKILL.md.
Output: one JSON object containing checks, blockers, cutoff_date, eligible, next_action.
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required and must be a date string")
    text = value.strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).date()
    except ValueError as exc:
        raise ValueError(f"{field} is not a supported date format") from exc


def subtract_six_calendar_months(value: date) -> date:
    month_index = value.month - 6
    year = value.year
    while month_index <= 0:
        month_index += 12
        year -= 1
    # A six-month subtraction from a late-month date uses the last valid day
    # of the destination month when that day does not exist.
    if month_index == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month_index + 1, 1)
    last_day = (next_month - date.resolution).day
    return date(year, month_index, min(value.day, last_day))


def age_on(dob: date, on_date: date) -> int:
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def get_count(payload: Dict[str, Any]) -> Tuple[Optional[int], Optional[str]]:
    explicit = payload.get("personal_checking_count")
    if explicit is not None:
        if isinstance(explicit, bool) or not isinstance(explicit, int) or explicit < 0:
            return None, "personal_checking_count must be a nonnegative integer"
        return explicit, None

    records = payload.get("checking_records")
    if not isinstance(records, list):
        return None, "provide personal_checking_count or checking_records"
    count = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict) or "counts_toward_limit" not in record:
            return None, f"checking_records[{index}] lacks counts_toward_limit"
        if not isinstance(record["counts_toward_limit"], bool):
            return None, f"checking_records[{index}].counts_toward_limit must be boolean"
        count += int(record["counts_toward_limit"])
    return count, None


def closure_check(records: Any, cutoff: date, complete: Any) -> Tuple[Optional[bool], List[str]]:
    issues: List[str] = []
    if complete is not True:
        return None, ["Closure-for-cause history for the prior six months is not complete."]
    if not isinstance(records, list):
        return None, ["checking_records must be a list when closure history is marked complete."]

    closed_for_cause_in_window = False
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            issues.append(f"checking_records[{index}] must be an object")
            continue
        cause = record.get("closed_for_cause")
        if cause not in (True, False):
            issues.append(f"checking_records[{index}].closed_for_cause must be true or false")
            continue
        if cause:
            try:
                closed_date = parse_date(record.get("closed_date"), f"checking_records[{index}].closed_date")
            except ValueError as exc:
                issues.append(str(exc))
                continue
            if closed_date >= cutoff:
                closed_for_cause_in_window = True
    if issues:
        return None, issues
    return (not closed_for_cause_in_window), []


def evaluate(payload: Dict[str, Any]) -> Dict[str, Any]:
    as_of = parse_date(payload.get("as_of"), "as_of")
    dob = parse_date(payload.get("date_of_birth"), "date_of_birth")
    if dob > as_of:
        raise ValueError("date_of_birth cannot be after as_of")

    cutoff = subtract_six_calendar_months(as_of)
    blockers: List[str] = []
    age = age_on(dob, as_of)

    verification_ok = payload.get("identity_verified") is True
    if not verification_ok:
        blockers.append("Identity verification has not been completed and logged.")

    age_ok = age >= 18
    if not age_ok:
        blockers.append("Customer must be at least 18 years old.")

    count, count_error = get_count(payload)
    limit_ok: Optional[bool]
    if count_error:
        limit_ok = None
        blockers.append(f"Personal checking account count is unresolved: {count_error}.")
    else:
        limit_ok = count < 4
        if not limit_ok:
            blockers.append("Customer already has four or more personal checking accounts.")

    closure_ok, closure_issues = closure_check(
        payload.get("checking_records"), cutoff, payload.get("closure_history_complete")
    )
    if closure_ok is None:
        blockers.extend(closure_issues)
    elif not closure_ok:
        blockers.append("A checking account was closed for cause within the prior six months.")

    eligible = verification_ok and age_ok and limit_ok is True and closure_ok is True
    return {
        "eligible": eligible,
        "next_action": "may_open_after_exact_class_confirmation" if eligible else "do_not_open",
        "as_of": as_of.isoformat(),
        "cutoff_date": cutoff.isoformat(),
        "checks": {
            "identity_verified": verification_ok,
            "age_years": age,
            "age_at_least_18": age_ok,
            "personal_checking_count": count,
            "under_four_personal_checking_accounts": limit_ok,
            "no_closed_for_cause_within_six_months": closure_ok,
        },
        "blockers": blockers,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"eligible": False, "next_action": "do_not_open", "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
