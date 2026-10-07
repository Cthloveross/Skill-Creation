#!/usr/bin/env python3
"""Evaluate objective personal-checking opening gates from supplied JSON.

Input and output schemas are documented in SKILL.md.  This program makes no
network calls and never executes a banking action.
"""

import json
import re
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Current-time strings may include a time and trailing timezone text.
    patterns = (
        "%m/%d/%Y",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S %Z",
    )
    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d").date()
        except ValueError:
            pass
    return None


def age_on(dob: date, today: date) -> int:
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def six_months_before(today: date) -> date:
    month = today.month - 6
    year = today.year
    if month <= 0:
        month += 12
        year -= 1
    # Preserve day where possible, otherwise use final day of target month.
    import calendar
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        print(json.dumps({"eligible_to_open": False, "checks": {},
                          "unknown_or_invalid": ["invalid JSON input: " + str(exc)]}))
        return

    unknown: List[str] = []
    checks: Dict[str, bool] = {}

    verified = payload.get("identity_verified")
    if not isinstance(verified, bool):
        unknown.append("identity_verified must be boolean")
        checks["identity_verified"] = False
    else:
        checks["identity_verified"] = verified

    dob = parse_date(payload.get("date_of_birth"))
    today = parse_date(payload.get("current_date"))
    if dob is None:
        unknown.append("valid date_of_birth is required")
    if today is None:
        unknown.append("valid current_date is required")
    if dob is not None and today is not None:
        if dob > today:
            unknown.append("date_of_birth is after current_date")
            checks["at_least_18"] = False
        else:
            checks["at_least_18"] = age_on(dob, today) >= 18
    else:
        checks["at_least_18"] = False

    accounts = payload.get("personal_checking_accounts")
    if not isinstance(accounts, list):
        unknown.append("personal_checking_accounts must be a list")
        accounts = []
        checks["prospective_personal_checking_count_at_most_4"] = False
        checks["no_closure_for_cause_in_past_6_months"] = False
    else:
        # Opening one more must not create more than four personal checking accounts.
        checks["prospective_personal_checking_count_at_most_4"] = len(accounts) + 1 <= 4
        closure_unknown = False
        recent_cause_closure = False
        if today is None:
            closure_unknown = True
        else:
            cutoff = six_months_before(today)
            for index, account in enumerate(accounts):
                if not isinstance(account, dict):
                    closure_unknown = True
                    unknown.append(f"account {index} is not an object")
                    continue
                status = account.get("status")
                cause = account.get("closed_for_cause")
                closed_date_value = account.get("closure_date")
                is_closed = isinstance(status, str) and status.strip().lower() in {
                    "closed", "close", "terminated"
                }
                # A closure record requires both cause and date to establish the rule.
                if is_closed or cause is True or closed_date_value not in (None, ""):
                    closure_date = parse_date(closed_date_value)
                    if not isinstance(cause, bool) or closure_date is None:
                        closure_unknown = True
                        unknown.append(f"account {index} lacks usable closure cause or closure date")
                    elif cause and closure_date >= cutoff and closure_date <= today:
                        recent_cause_closure = True
        checks["no_closure_for_cause_in_past_6_months"] = (
            not recent_cause_closure and not closure_unknown
        )

    eligible = bool(checks) and all(checks.values()) and not unknown
    output = {
        "eligible_to_open": eligible,
        "checks": checks,
        "unknown_or_invalid": unknown,
        "personal_checking_count": len(accounts),
        "prospective_personal_checking_count": len(accounts) + 1,
    }
    if dob is not None and today is not None and dob <= today:
        output["age"] = age_on(dob, today)
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
