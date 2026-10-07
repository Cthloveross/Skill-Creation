#!/usr/bin/env python3
"""Evaluate supplied general eligibility facts for a personal checking account.

Input JSON object:
  verified: bool
  personal_checking_count: nonnegative int
  closed_for_cause_past_6_months: bool
  account_class: nonempty str
  selection_confirmed: bool
  age: nonnegative int (optional), or
  date_of_birth: MM/DD/YYYY or YYYY-MM-DD and as_of: YYYY-MM-DD

Output JSON object:
  eligible: bool
  age: int or null
  reasons: list[str]
  error: "invalid_input" (only for malformed input)
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def invalid(reason: str) -> Dict[str, Any]:
    return {
        "eligible": False,
        "age": None,
        "reasons": [reason],
        "error": "invalid_input",
    }


def parse_date(value: Any, formats: List[str]) -> date:
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("date has an unsupported format")


def calculate_age(dob: date, on_date: date) -> int:
    if dob > on_date:
        raise ValueError("date_of_birth cannot be in the future")
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def evaluate(data: Dict[str, Any]) -> Dict[str, Any]:
    for field in ("verified", "closed_for_cause_past_6_months", "selection_confirmed"):
        if not isinstance(data.get(field), bool):
            return invalid(f"{field} must be a boolean")

    count = data.get("personal_checking_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return invalid("personal_checking_count must be a nonnegative integer")

    account_class = data.get("account_class")
    if not isinstance(account_class, str) or not account_class.strip():
        return invalid("account_class must be a nonempty string")

    age: Optional[int]
    if data.get("age") is not None:
        candidate = data["age"]
        if isinstance(candidate, bool) or not isinstance(candidate, int) or candidate < 0:
            return invalid("age must be a nonnegative integer")
        age = candidate
    else:
        try:
            dob = parse_date(data.get("date_of_birth"), ["%m/%d/%Y", "%Y-%m-%d"])
            as_of = parse_date(data.get("as_of"), ["%Y-%m-%d"])
            age = calculate_age(dob, as_of)
        except ValueError as exc:
            return invalid(str(exc))

    reasons: List[str] = []
    if not data["verified"]:
        reasons.append("Customer identity is not verified.")
    if age < 18:
        reasons.append("Customer must be at least 18 years old for a personal checking account.")
    if count > 4:
        reasons.append("Customer exceeds the maximum of four personal checking accounts.")
    if data["closed_for_cause_past_6_months"]:
        reasons.append("Customer has a checking account closed for cause within the past six months.")
    if not data["selection_confirmed"]:
        reasons.append("Customer has not confirmed the requested account class.")

    return {"eligible": not reasons, "age": age, "reasons": reasons}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        print(json.dumps(invalid("stdin must contain a JSON object"), sort_keys=True))
        return

    if not isinstance(payload, dict):
        print(json.dumps(invalid("stdin must contain a JSON object"), sort_keys=True))
        return

    print(json.dumps(evaluate(payload), sort_keys=True))


if __name__ == "__main__":
    main()
