#!/usr/bin/env python3
"""Assess stated numeric requirements and a formation-age eligibility gate.

Reads one JSON object from stdin and writes one JSON object to stdout. Product
terms are entirely caller-supplied so the helper is reusable across account
catalogs.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a nonnegative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a nonnegative number") from exc
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative number")
    return result


def as_json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def main(payload: dict[str, Any]) -> dict[str, Any]:
    requirements = payload.get("requirements")
    candidate = payload.get("candidate")
    if not isinstance(requirements, dict) or not isinstance(candidate, dict):
        raise ValueError("requirements and candidate must be objects")

    zero_required = requirements.get("zero_overdraft_required", False)
    if not isinstance(zero_required, bool):
        raise ValueError("zero_overdraft_required must be a boolean")

    minimum_rebate = number(requirements.get("minimum_atm_rebate", 0), "minimum_atm_rebate")
    overdraft_fee = number(candidate.get("overdraft_fee"), "candidate.overdraft_fee")
    rebate_cap = number(candidate.get("monthly_atm_rebate_cap"), "candidate.monthly_atm_rebate_cap")

    requirements_met = {
        "zero_overdraft": (overdraft_fee == 0) if zero_required else True,
        "minimum_atm_rebate": rebate_cap >= minimum_rebate,
    }

    eligibility = candidate.get("eligibility", {})
    if not isinstance(eligibility, dict):
        raise ValueError("candidate.eligibility must be an object")
    maximum_age_raw = eligibility.get("max_formation_age_years")
    age_raw = payload.get("company_formation_age_years")

    if maximum_age_raw is None:
        eligibility_state = "not_applicable"
        question = None
    else:
        maximum_age = number(maximum_age_raw, "candidate.eligibility.max_formation_age_years")
        if age_raw is None:
            eligibility_state = "unknown"
            question = "Was the business formed within the account's stated eligibility period?"
        else:
            age = number(age_raw, "company_formation_age_years")
            eligibility_state = "met" if age <= maximum_age else "not_met"
            question = None

    feature_match = all(requirements_met.values())
    eligible = eligibility_state in ("met", "not_applicable")
    return {
        "candidate_name": candidate.get("name"),
        "requirements_met": requirements_met,
        "feature_match": feature_match,
        "eligibility": eligibility_state,
        "recommendable": feature_match and eligible,
        "follow_up_question": question,
        "evaluated_values": {
            "overdraft_fee": as_json_number(overdraft_fee),
            "monthly_atm_rebate_cap": as_json_number(rebate_cap),
            "minimum_atm_rebate_requested": as_json_number(minimum_rebate),
        },
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), separators=(",", ":"), ensure_ascii=False))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")))
        sys.exit(2)
