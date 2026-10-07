#!/usr/bin/env python3
"""Assess supplied evidence for opening a personal checking account.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper
never calls banking tools and treats unknown evidence as a blocker rather than
assuming eligibility.
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def parse_date(value: Any) -> Optional[date]:
    """Parse a date or the leading date portion of an ISO-like timestamp."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    return None


def age_on(dob: date, on_date: date) -> int:
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def require_boolean(data: Dict[str, Any], key: str, missing: List[str], blockers: List[str], label: str) -> bool:
    value = data.get(key)
    if value is True:
        return True
    if value is False:
        blockers.append(label)
    else:
        missing.append(key)
    return False


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"eligible_to_continue": False, "error": "invalid_json", "detail": str(exc)}))
        return

    if not isinstance(data, dict):
        print(json.dumps({"eligible_to_continue": False, "error": "input_must_be_object"}))
        return

    checks: Dict[str, Any] = {}
    blockers: List[str] = []
    missing: List[str] = []

    dob = parse_date(data.get("date_of_birth"))
    as_of = parse_date(data.get("as_of"))
    if dob is None:
        missing.append("date_of_birth")
        checks["age_18_or_older"] = None
    elif as_of is None:
        missing.append("as_of")
        checks["age_18_or_older"] = None
    elif dob > as_of:
        checks["age_18_or_older"] = False
        blockers.append("date_of_birth is after as_of")
    else:
        computed_age = age_on(dob, as_of)
        checks["age_18_or_older"] = computed_age >= 18
        checks["age_years"] = computed_age
        if computed_age < 18:
            blockers.append("customer is under 18")

    checks["identity_verified"] = require_boolean(
        data, "identity_verified", missing, blockers, "identity has not been verified"
    )
    checks["authority_confirmed"] = require_boolean(
        data, "authority_confirmed", missing, blockers, "customer authority has not been confirmed"
    )
    checks["official_account_class_confirmed"] = require_boolean(
        data, "official_account_class_confirmed", missing, blockers,
        "an official account class has not been confirmed"
    )
    checks["final_opening_consent"] = require_boolean(
        data, "final_opening_consent", missing, blockers,
        "final consent to open the account has not been obtained"
    )

    count = data.get("existing_personal_checking_count")
    resulting_count = None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        missing.append("existing_personal_checking_count")
        checks["resulting_personal_checking_count_at_most_4"] = None
    else:
        resulting_count = count + 1
        checks["resulting_personal_checking_count_at_most_4"] = resulting_count <= 4
        if resulting_count > 4:
            blockers.append("opening this account would result in more than four personal checking accounts")

    closure_review = data.get("closures_for_cause_within_last_6_months")
    if closure_review is None:
        missing.append("closures_for_cause_within_last_6_months")
        checks["no_recent_closure_for_cause"] = None
    elif not isinstance(closure_review, bool):
        missing.append("closures_for_cause_within_last_6_months")
        checks["no_recent_closure_for_cause"] = None
    else:
        checks["no_recent_closure_for_cause"] = not closure_review
        if closure_review:
            blockers.append("a checking account was closed for cause within the last six months")

    funding_required = data.get("funding_required")
    funding_verified = data.get("funding_verified")
    if not isinstance(funding_required, bool):
        missing.append("funding_required")
        checks["required_funding_verified"] = None
    elif not funding_required:
        checks["required_funding_verified"] = True
    elif funding_verified is True:
        checks["required_funding_verified"] = True
    elif funding_verified is False:
        checks["required_funding_verified"] = False
        blockers.append("required opening funding is not verified")
    else:
        checks["required_funding_verified"] = None
        missing.append("funding_verified")

    eligible = (
        not blockers
        and not missing
        and all(value is True for key, value in checks.items() if key != "age_years")
    )
    result = {
        "eligible_to_continue": eligible,
        "checks": checks,
        "resulting_personal_checking_count": resulting_count,
        "blocking_reasons": blockers,
        "missing_evidence": missing,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
