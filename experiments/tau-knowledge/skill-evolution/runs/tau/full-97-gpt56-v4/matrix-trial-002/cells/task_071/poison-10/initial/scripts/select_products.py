#!/usr/bin/env python3
"""Filter documented business-account candidates.

Reads one JSON object from stdin and writes one JSON object to stdout.  The
schema is described in SKILL.md.  This program intentionally does not fetch
product facts or initiate banking actions.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def decimal_value(value, label, errors):
    if value is None or isinstance(value, bool):
        errors.append(f"{label} is missing or is not a decimal value")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{label} is not a valid decimal value")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(f"{label} must be a non-negative finite decimal")
        return None
    return parsed


def parse_date(value, label, errors):
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{label} must use YYYY-MM-DD")
        return None


def rank_value(candidate, key):
    value = candidate.get(key)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 10 ** 12


def active_promotion_rank(candidate, as_of, errors, label):
    rank = candidate.get("promotion_rank")
    if rank is None:
        return 10 ** 12
    if not isinstance(rank, int) or isinstance(rank, bool) or rank < 0:
        errors.append(f"{label}.promotion_rank must be a non-negative integer")
        return 10 ** 12
    start = parse_date(candidate.get("promotion_start"), f"{label}.promotion_start", errors)
    end = parse_date(candidate.get("promotion_end"), f"{label}.promotion_end", errors)
    if as_of is None or start is None or end is None or start > end:
        if start is not None and end is not None and start > end:
            errors.append(f"{label} has an invalid promotion date range")
        return 10 ** 12
    return rank if start <= as_of <= end else 10 ** 12


def candidate_name(candidate, label, errors):
    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{label}.name is required")
        return None
    return name.strip()


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"error": "input must be a JSON object"}

    requirements = payload.get("requirements", {})
    if not isinstance(requirements, dict):
        return {"error": "requirements must be an object"}
    checking_req = requirements.get("checking", {}) or {}
    savings_req = requirements.get("savings", {}) or {}
    if not isinstance(checking_req, dict) or not isinstance(savings_req, dict):
        return {"error": "checking and savings requirements must be objects"}

    as_of = parse_date(payload.get("as_of"), "as_of", errors)
    checking_min = None
    if "mobile_deposit_daily_min" in checking_req:
        checking_min = decimal_value(checking_req["mobile_deposit_daily_min"], "requirements.checking.mobile_deposit_daily_min", errors)
    savings_same_day = savings_req.get("same_day_ach_required")
    if savings_same_day is not None and not isinstance(savings_same_day, bool):
        errors.append("requirements.savings.same_day_ach_required must be boolean")

    checking_candidates = payload.get("checking_candidates", [])
    savings_candidates = payload.get("savings_candidates", [])
    if not isinstance(checking_candidates, list) or not isinstance(savings_candidates, list):
        return {"error": "candidate collections must be arrays"}

    qualifying_checking = []
    if checking_min is not None:
        for index, candidate in enumerate(checking_candidates):
            label = f"checking_candidates[{index}]"
            if not isinstance(candidate, dict):
                errors.append(f"{label} must be an object")
                continue
            name = candidate_name(candidate, label, errors)
            limit = decimal_value(candidate.get("mobile_deposit_daily_limit"), f"{label}.mobile_deposit_daily_limit", errors)
            if name is not None and limit is not None and limit >= checking_min:
                qualifying_checking.append((candidate, name, limit, index))

    qualifying_savings = []
    if savings_same_day is True:
        for index, candidate in enumerate(savings_candidates):
            label = f"savings_candidates[{index}]"
            if not isinstance(candidate, dict):
                errors.append(f"{label} must be an object")
                continue
            name = candidate_name(candidate, label, errors)
            same_day = candidate.get("same_day_ach")
            if not isinstance(same_day, bool):
                errors.append(f"{label}.same_day_ach must be boolean")
                continue
            if name is not None and same_day:
                qualifying_savings.append((candidate, name, index))

    qualifying_checking.sort(key=lambda row: (
        active_promotion_rank(row[0], as_of, errors, f"checking_candidates[{row[3]}]"),
        rank_value(row[0], "preference_rank"), row[3]
    ))
    qualifying_savings.sort(key=lambda row: (rank_value(row[0], "preference_rank"), row[2]))

    result = {
        "checking": {
            "required": checking_min is not None,
            "qualifying": [{"name": row[1], "mobile_deposit_daily_limit": str(row[2])} for row in qualifying_checking],
            "selected": None if not qualifying_checking else {"name": qualifying_checking[0][1], "mobile_deposit_daily_limit": str(qualifying_checking[0][2])}
        },
        "savings": {
            "required": savings_same_day is True,
            "qualifying": [row[1] for row in qualifying_savings],
            "selected": None if not qualifying_savings else qualifying_savings[0][1]
        },
        "validation_errors": errors
    }
    return result


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        print(json.dumps(main(supplied), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON input: {exc.msg}"}))
        sys.exit(2)
