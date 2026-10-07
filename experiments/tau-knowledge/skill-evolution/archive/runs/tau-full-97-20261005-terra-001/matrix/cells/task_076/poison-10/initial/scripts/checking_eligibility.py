#!/usr/bin/env python3
"""Evaluate general personal-checking eligibility from supplied facts.

Input JSON:
  {
    "verified": bool,
    "personal_checking_count": nonnegative int,
    "closed_for_cause_past_6_months": bool,
    "account_class": nonempty str,
    "selection_confirmed": bool,
    "age": nonnegative int (optional),
    "date_of_birth": "MM/DD/YYYY" or "YYYY-MM-DD" (required if age absent),
    "as_of": "YYYY-MM-DD" (required if age absent)
  }

Output JSON on success:
  {"eligible": bool, "age": int|null, "reasons": [str]}
Output JSON on invalid input:
  {"eligible": false, "age": null, "reasons": [...], "error": "invalid_input"}
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def parse_date(value: Any, formats: List[str]) -> date:
    if not isinstance(value, str):
        raise ValueError("date must be a string")
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date has an unsupported format")


def age_on(dob: date, on_date: date) -> int:
    if dob > on_date:
        raise ValueError("date_of_birth cannot be in the future")
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def invalid(message: str) -> Dict[str, Any]:
    return {"eligible": False, "age": None, "reasons": [message], "error": "invalid_input"}


def evaluate(data: Dict[str, Any]) -> Dict[str, Any]:
    required_bools = ["verified", "closed_for_cause_past_6_months", "selection_confirmed"]
    for field in required_bools:
        if not isinstance(data.get(field), bool):
            return invalid(f"{field} must be a boolean")

    count = data.get("personal_checking_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return invalid("personal_checking_count must be a nonnegative integer")

    account_class = data.get("account_class")
    if not isinstance(account_class, str) or not account_class.strip():
        return invalid("account_class must be a nonempty string")

    calculated_age: Optional[int]
    if "age" in data and data["age"] is not None:
        supplied_age = data["age"]
        if isinstance(supplied_age, bool) or not isinstance(supplied_age, int) or supplied_age < 0:
            return invalid("age must be a nonnegative integer")
        calculated_age = supplied_age
    else:
        try:
            dob = parse_date(data.get("date_of_birth"), ["%m/%d/%Y", "%Y-%m-%d"])
            on_date = parse_date(data.get("as_of"), ["%Y-%m-%d"])
            calculated_age = age_on(dob, on_date)
        except ValueError as exc:
            return invalid(str(exc))

    reasons: List[str] = []
    if not data["verified"]:
        reasons.append("Customer identity is not verified.")
    if calculated_age < 18:
        reasons.append("Customer must be at least 18 years old for a personal checking account.")
    if count > 4:
        reasons.append("Customer already has more than four personal checking accounts.")
    if data["closed_for_cause_past_6_months"]:
        reasons.append("Customer has a checking account closed for cause within the past six months.")
    if not data["selection_confirmed"]:
        reasons.append("Customer has not confirmed the requested account class.")

    return {"eligible": not reasons, "age": calculated_age, "reasons": reasons}


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
