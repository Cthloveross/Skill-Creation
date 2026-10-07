#!/usr/bin/env python3
"""Assess personal-checking opening prerequisites from normalized runtime data.

Input JSON object:
{
  "as_of": "YYYY-MM-DD" | "YYYY-MM-DD HH:MM:SS TZ" | "MM/DD/YYYY",
  "date_of_birth": "YYYY-MM-DD" | "MM/DD/YYYY",
  "identity_verified": true | false,
  "desired_account_class": "full official class selected by customer" | null,
  "official_name_confirmed": true | false,
  "closure_history_confirmed": true | false,
  "closure_for_cause_last_6_months": true | false | null,
  "accounts": [
    {"is_personal_checking": true | false, "status": "open|closed|...",
     "closed_for_cause": true | false | null,
     "closed_at": "YYYY-MM-DD" | null}
  ]
}

`accounts` must be normalized by the caller. The script counts records whose
`is_personal_checking` is exactly true. `closure_for_cause_last_6_months` is the
caller-confirmed authoritative result when available. When it is null, the script
also examines supplied closed-for-cause records with usable dates, but reports an
unknown decision unless closure_history_confirmed is true.

Output JSON includes age_years, personal_checking_count,
recent_for_cause_closures, decision (eligible, ineligible, or unknown), and
blocking reasons. It performs no banking action.
"""
import calendar
import datetime as dt
import json
import sys
from typing import Any, Dict, List, Optional


def parse_date(value: Any, field: str) -> dt.date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required and must be a date string")
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S %Z"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    # Supports ISO timestamps including an offset.
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise ValueError(f"{field} has an unsupported date format: {text!r}") from exc


def add_months(value: dt.date, months: int) -> dt.date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def age_on(dob: dt.date, on_date: dt.date) -> int:
    return on_date.year - dob.year - ((on_date.month, on_date.day) < (dob.month, dob.day))


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    as_of = parse_date(payload.get("as_of"), "as_of")
    dob = parse_date(payload.get("date_of_birth"), "date_of_birth")
    if dob > as_of:
        raise ValueError("date_of_birth cannot be after as_of")

    accounts = payload.get("accounts", [])
    if not isinstance(accounts, list):
        raise ValueError("accounts must be an array")

    checking_accounts = [a for a in accounts if isinstance(a, dict) and a.get("is_personal_checking") is True]
    cutoff = add_months(as_of, -6)
    dated_recent_closures = 0
    unusable_closure_record = False
    for account in checking_accounts:
        if account.get("closed_for_cause") is True:
            try:
                closed_at = parse_date(account.get("closed_at"), "accounts[].closed_at")
            except ValueError:
                unusable_closure_record = True
                continue
            if cutoff <= closed_at <= as_of:
                dated_recent_closures += 1

    authoritative_closure = payload.get("closure_for_cause_last_6_months")
    if authoritative_closure not in (True, False, None):
        raise ValueError("closure_for_cause_last_6_months must be true, false, or null")
    closure_confirmed = payload.get("closure_history_confirmed") is True
    if authoritative_closure is True:
        recent_closures: Optional[int] = max(1, dated_recent_closures)
    elif authoritative_closure is False and closure_confirmed:
        recent_closures = 0
    elif closure_confirmed and not unusable_closure_record:
        recent_closures = dated_recent_closures
    else:
        recent_closures = None

    age = age_on(dob, as_of)
    reasons: List[str] = []
    unknowns: List[str] = []
    if payload.get("identity_verified") is not True:
        reasons.append("Identity has not been verified.")
    if age < 18:
        reasons.append("Customer is under 18.")
    if len(checking_accounts) >= 4:
        reasons.append("Customer already has four or more personal checking accounts.")
    if recent_closures is not None and recent_closures > 0:
        reasons.append("A checking account was closed for cause within the preceding six calendar months.")
    if recent_closures is None:
        unknowns.append("Closure-for-cause history for the preceding six calendar months is not confirmed.")
    if not isinstance(payload.get("desired_account_class"), str) or not payload["desired_account_class"].strip():
        reasons.append("No desired account class has been selected.")
    if payload.get("official_name_confirmed") is not True:
        unknowns.append("The selected account class has not been confirmed as its full official name.")

    if reasons:
        decision = "ineligible"
    elif unknowns:
        decision = "unknown"
    else:
        decision = "eligible"

    return {
        "as_of": as_of.isoformat(),
        "age_years": age,
        "personal_checking_count": len(checking_accounts),
        "six_month_cutoff": cutoff.isoformat(),
        "recent_for_cause_closures": recent_closures,
        "decision": decision,
        "blocking_reasons": reasons,
        "unknown_requirements": unknowns,
        "opening_tool_may_be_called": decision == "eligible",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
