#!/usr/bin/env python3
"""Deterministically assess checking-referral prerequisites and program ranking.

Reads one JSON object from stdin and writes one JSON object to stdout.  The
program catalog and customer facts are supplied by the caller; no bank data is
embedded in this file.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


REQUIRED_REFERRED_BOOLEAN_RULES = {
    "has_no_rho_accounts_or_closed_last_12_months": True,
    "same_registered_address": False,
    "verified": True,
    "closed_for_cause_last_6_months": False,
    "deposit_is_new_money": True,
    "will_keep_qualifying_deposit_30_days_after_window": True,
    "using_other_new_account_promotion": False,
    "account_in_good_standing": True,
}


def parse_datetime(value: Any, field: str, require_time: bool = False) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO-8601 string")
    raw = value.strip()
    if require_time and "T" not in raw and " " not in raw:
        raise ValueError(f"{field} must include an exact time, not only a date")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        # A supplied local time is usable for date-based tenure only. The caller
        # must supply a consistent timezone for exact rolling-window evaluation.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def issue_for_boolean(container: Dict[str, Any], field: str, expected: bool,
                      target: List[str], label: str) -> None:
    value = container.get(field)
    if value is None:
        target.append(f"Unknown: {label}.")
    elif not isinstance(value, bool):
        target.append(f"Invalid value for {label}; it must be true, false, or null.")
    elif value != expected:
        if expected:
            target.append(f"Ineligible: {label} is not satisfied.")
        else:
            target.append(f"Ineligible: {label} must be false.")


def is_unknown(issues: List[str]) -> bool:
    return any(item.startswith("Unknown:") or item.startswith("Invalid value") for item in issues)


def is_confirmed_ineligible(issues: List[str]) -> bool:
    return any(item.startswith("Ineligible:") for item in issues)


def validate_programs(programs: Any, errors: List[str]) -> List[Dict[str, Any]]:
    if not isinstance(programs, list) or not programs:
        errors.append("programs must be a nonempty array")
        return []
    seen = set()
    valid: List[Dict[str, Any]] = []
    numeric_fields = [
        "referrer_bonus", "referred_bonus", "min_deposit", "deposit_window_days",
        "referrer_tenure_days", "annual_cap",
    ]
    for index, program in enumerate(programs):
        prefix = f"programs[{index}]"
        if not isinstance(program, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = program.get("account_type")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.account_type must be a nonempty string")
            continue
        if name in seen:
            errors.append(f"Duplicate account_type: {name}")
        seen.add(name)
        for field in numeric_fields:
            value = program.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                errors.append(f"{prefix}.{field} must be a nonnegative number")
        for field in ("recipient_min_age", "recipient_max_age"):
            if field in program and (not isinstance(program[field], (int, float)) or
                                     isinstance(program[field], bool) or program[field] < 0):
                errors.append(f"{prefix}.{field} must be a nonnegative number when supplied")
        valid.append(program)
    return valid


def evaluate_referrer(referrer: Dict[str, Any], now: datetime) -> Tuple[List[str], Optional[int], Optional[int]]:
    issues: List[str] = []
    tenure_days: Optional[int] = None
    rolling_count: Optional[int] = None

    earliest = referrer.get("earliest_checking_opened")
    if earliest is None:
        issues.append("Unknown: earliest checking-account opening date needed for tenure.")
    else:
        try:
            opened = parse_datetime(earliest, "referrer.earliest_checking_opened")
            if opened > now:
                issues.append("Ineligible: earliest checking-account opening date is in the future.")
            else:
                tenure_days = (now - opened).days
        except ValueError as exc:
            issues.append(f"Invalid value for earliest checking-account opening date: {exc}.")

    issue_for_boolean(referrer, "account_in_good_standing", True, issues,
                      "referrer account good-standing requirement")

    events = referrer.get("successful_bonus_events")
    if events is None:
        issues.append("Unknown: complete successful-bonus history needed for rolling nine-day cap.")
    elif not isinstance(events, list):
        issues.append("Invalid value for successful_bonus_events; it must be an array or null.")
    else:
        rolling_count = 0
        window_start = now - timedelta(days=9)
        for index, event in enumerate(events):
            if not isinstance(event, dict):
                issues.append(f"Invalid value for successful_bonus_events[{index}].")
                continue
            status = event.get("status", "COMPLETE")
            if status != "COMPLETE":
                continue
            try:
                timestamp = parse_datetime(event.get("timestamp"),
                                           f"successful_bonus_events[{index}].timestamp",
                                           require_time=True)
            except ValueError as exc:
                issues.append(f"Unknown: exact timestamp needed for rolling cap ({exc}).")
                continue
            if timestamp > now:
                issues.append("Invalid value: successful-bonus event is in the future.")
            elif timestamp >= window_start:
                rolling_count += 1
        if rolling_count >= 2:
            issues.append("Ineligible: two successful referral bonuses already fall in the rolling nine-day window.")
    return issues, tenure_days, rolling_count


def evaluate_referred(referred: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    for field, expected in REQUIRED_REFERRED_BOOLEAN_RULES.items():
        readable = field.replace("_", " ")
        issue_for_boolean(referred, field, expected, issues, readable)

    count = referred.get("existing_personal_checking_count")
    if count is None:
        issues.append("Unknown: existing personal checking-account count.")
    elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
        issues.append("Invalid value for existing personal checking-account count.")
    elif count >= 4:
        issues.append("Ineligible: prospective customer is at the four-account personal checking limit.")
    return issues


def evaluate_program(program: Dict[str, Any], expected_deposit: Any, tenure_days: Optional[int],
                     annual_counts: Any, referred: Dict[str, Any]) -> List[str]:
    issues: List[str] = []
    name = program["account_type"]
    if expected_deposit is None:
        issues.append("Unknown: actual qualifying deposit amount.")
    elif not isinstance(expected_deposit, (int, float)) or isinstance(expected_deposit, bool) or expected_deposit < 0:
        issues.append("Invalid value for expected_deposit.")
    elif expected_deposit < program["min_deposit"]:
        issues.append("Ineligible: expected deposit is below this program's qualifying deposit.")

    if tenure_days is None:
        issues.append("Unknown: referrer tenure cannot be compared with this program.")
    elif tenure_days < program["referrer_tenure_days"]:
        issues.append("Ineligible: referrer has not met this program's tenure threshold.")

    if annual_counts is None:
        issues.append("Unknown: calendar-year successful-referral count for this program.")
    elif not isinstance(annual_counts, dict):
        issues.append("Invalid value for annual_successful_bonus_counts.")
    else:
        count = annual_counts.get(name)
        if count is None:
            issues.append("Unknown: calendar-year successful-referral count for this program.")
        elif not isinstance(count, int) or isinstance(count, bool) or count < 0:
            issues.append("Invalid value for calendar-year successful-referral count.")
        elif count >= program["annual_cap"]:
            issues.append("Ineligible: this program's calendar-year referral cap has been reached.")

    age = referred.get("age")
    if age is None:
        issues.append("Unknown: prospective customer age for account eligibility.")
    elif not isinstance(age, (int, float)) or isinstance(age, bool) or age < 0:
        issues.append("Invalid value for prospective customer age.")
    else:
        minimum = program.get("recipient_min_age", 18)
        maximum = program.get("recipient_max_age")
        if age < minimum:
            issues.append("Ineligible: prospective customer is below this account's minimum age.")
        if maximum is not None and age > maximum:
            issues.append("Ineligible: prospective customer exceeds this account's maximum age.")
        if age < 18 and program.get("guardian_required_if_under_18", False):
            issue_for_boolean(referred, "guardian_available", True, issues,
                              "guardian availability for minor account holder")
    return issues


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    try:
        now = parse_datetime(payload.get("now"), "now", require_time=True)
    except ValueError as exc:
        return {"decision": "blocked", "input_errors": [str(exc)]}

    programs = validate_programs(payload.get("programs"), errors)
    referrer = payload.get("referrer")
    referred = payload.get("referred")
    if not isinstance(referrer, dict):
        errors.append("referrer must be an object")
        referrer = {}
    if not isinstance(referred, dict):
        errors.append("referred must be an object")
        referred = {}
    if errors:
        return {"decision": "blocked", "input_errors": errors}

    referrer_issues, tenure_days, rolling_count = evaluate_referrer(referrer, now)
    referred_issues = evaluate_referred(referred)
    base = {
        "referrer_issues": referrer_issues,
        "referred_issues": referred_issues,
        "referrer_tenure_days": tenure_days,
        "rolling_successful_bonus_count": rolling_count,
    }

    # Mandatory policy gate: no ranking while referrer eligibility is unresolved
    # or failed. Prospective-customer unknowns also block any safe selection.
    all_base_issues = referrer_issues + referred_issues
    if is_unknown(all_base_issues):
        base.update({"decision": "blocked", "best_programs": [], "program_results": []})
        return base
    if is_confirmed_ineligible(all_base_issues):
        base.update({"decision": "ineligible", "best_programs": [], "program_results": []})
        return base

    results: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    for program in programs:
        issues = evaluate_program(program, payload.get("expected_deposit"), tenure_days,
                                  referrer.get("annual_successful_bonus_counts"), referred)
        result = {
            "account_type": program["account_type"],
            "combined_bonus": program["referrer_bonus"] + program["referred_bonus"],
            "qualifying_deposit": program["min_deposit"],
            "deposit_window_days": program["deposit_window_days"],
            "referrer_tenure_days": program["referrer_tenure_days"],
            "annual_cap": program["annual_cap"],
            "issues": issues,
        }
        results.append(result)
        if not issues:
            eligible.append(result)

    if any(is_unknown(item["issues"]) for item in results):
        base.update({"decision": "blocked", "program_results": results, "best_programs": []})
        return base
    if not eligible:
        base.update({"decision": "ineligible", "program_results": results, "best_programs": []})
        return base

    highest = max(item["combined_bonus"] for item in eligible)
    best = [item for item in eligible if item["combined_bonus"] == highest]
    base.update({"decision": "eligible", "program_results": results, "best_programs": best})
    return base


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("Top-level JSON value must be an object")
        response = main(request)
    except (json.JSONDecodeError, ValueError) as exc:
        response = {"decision": "blocked", "input_errors": [str(exc)]}
    print(json.dumps(response, sort_keys=True, separators=(",", ":")))
