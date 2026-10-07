#!/usr/bin/env python3
"""Evaluate referral-program eligibility from explicitly confirmed facts.

Reads a JSON object from stdin and writes a JSON object to stdout.  This script
never treats absent information as a passed requirement and never performs a
banking action.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

REQUIRED_COMMON_CHECKS = (
    "identity_verified",
    "new_customer",
    "different_registered_address",
    "distinct_business_primary_owner",
    "new_money_confirmed",
    "both_accounts_good_standing",
    "promotion_stacking_clear",
    "recent_bonus_history_verified",
)


def parse_instant(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"{field} must include a UTC offset")
    return moment.astimezone(timezone.utc)


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if amount < 0:
        raise ValueError(f"{field} cannot be negative")
    return amount


def optional_nonnegative_int(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer or null")
    return value


def check_state(value, label, blockers, unknowns):
    if value is True:
        return
    if value is False:
        blockers.append(label)
    else:
        unknowns.append(label)


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_instant(data.get("as_of"), "as_of")
    programs = data.get("programs")
    if not isinstance(programs, list) or not programs:
        raise ValueError("programs must be a nonempty array")

    common_checks = data.get("common_checks")
    if not isinstance(common_checks, dict):
        raise ValueError("common_checks must be an object")
    common_blockers, common_unknowns = [], []
    for key in REQUIRED_COMMON_CHECKS:
        check_state(common_checks.get(key), key, common_blockers, common_unknowns)

    history = data.get("recent_successful_bonus_timestamps")
    rolling_count = None
    if history is None:
        if "recent_bonus_history_verified" not in common_unknowns:
            common_unknowns.append("recent_successful_bonus_timestamps")
    elif not isinstance(history, list):
        raise ValueError("recent_successful_bonus_timestamps must be an array or null")
    else:
        cutoff = as_of - timedelta(days=9)
        rolling_count = 0
        for index, item in enumerate(history):
            instant = parse_instant(item, f"recent_successful_bonus_timestamps[{index}]")
            if cutoff <= instant <= as_of:
                rolling_count += 1
        if rolling_count >= 2:
            common_blockers.append("two_bonus_rolling_9_day_cap")

    deposit_raw = data.get("confirmed_new_money_deposit")
    deposit = None if deposit_raw is None else decimal_value(deposit_raw, "confirmed_new_money_deposit")
    tenure = optional_nonnegative_int(data.get("referrer_tenure_days"), "referrer_tenure_days")
    annual_counts = data.get("annual_bonus_counts")
    if annual_counts is not None and not isinstance(annual_counts, dict):
        raise ValueError("annual_bonus_counts must be an object or null")
    program_checks = data.get("program_checks", {})
    if not isinstance(program_checks, dict):
        raise ValueError("program_checks must be an object")

    evaluated = []
    for index, program in enumerate(programs):
        if not isinstance(program, dict):
            raise ValueError(f"programs[{index}] must be an object")
        name = program.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"programs[{index}].name must be a nonempty string")
        bonus = decimal_value(program.get("referrer_bonus"), f"programs[{index}].referrer_bonus")
        required_deposit = decimal_value(program.get("required_deposit"), f"programs[{index}].required_deposit")
        tenure_needed = optional_nonnegative_int(program.get("tenure_days"), f"programs[{index}].tenure_days")
        if tenure_needed is None:
            raise ValueError(f"programs[{index}].tenure_days is required")
        window = optional_nonnegative_int(program.get("deposit_window_days"), f"programs[{index}].deposit_window_days")
        if window is None or window == 0:
            raise ValueError(f"programs[{index}].deposit_window_days must be positive")

        blockers, unknowns = [], []
        if deposit is None:
            unknowns.append("confirmed_new_money_deposit")
        elif deposit < required_deposit:
            blockers.append("qualifying_deposit_below_requirement")
        if tenure is None:
            unknowns.append("earliest_checking_tenure")
        elif tenure < tenure_needed:
            blockers.append("earliest_checking_tenure_below_requirement")

        limit = program.get("annual_limit")
        if limit is not None:
            limit = optional_nonnegative_int(limit, f"programs[{index}].annual_limit")
            count = None if annual_counts is None else annual_counts.get(name)
            count = optional_nonnegative_int(count, f"annual_bonus_counts[{name}]")
            if count is None:
                unknowns.append("current_calendar_year_bonus_count")
            elif count >= limit:
                blockers.append("annual_referral_bonus_cap")

        specific = program_checks.get(name, True)
        check_state(specific, "product_specific_eligibility", blockers, unknowns)
        evaluated.append({
            "name": name,
            "referrer_bonus": str(bonus),
            "required_deposit": str(required_deposit),
            "deposit_window_days": window,
            "tenure_days": tenure_needed,
            "blockers": blockers,
            "unknowns": unknowns,
            "eligible": not blockers and not unknowns,
        })

    common_clear = not common_blockers and not common_unknowns
    eligible = [item for item in evaluated if item["eligible"]]
    recommendation = None
    if common_clear and eligible:
        recommendation = max(eligible, key=lambda item: (Decimal(item["referrer_bonus"]), item["name"]))
        decision = "recommendation_ready"
    elif common_blockers or common_unknowns:
        decision = "defer"
    else:
        decision = "no_qualifying_program"

    return {
        "decision": decision,
        "rolling_successful_bonus_count_last_9_days": rolling_count,
        "common_blockers": common_blockers,
        "common_unknowns": common_unknowns,
        "programs": evaluated,
        "recommended_program": recommendation,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
