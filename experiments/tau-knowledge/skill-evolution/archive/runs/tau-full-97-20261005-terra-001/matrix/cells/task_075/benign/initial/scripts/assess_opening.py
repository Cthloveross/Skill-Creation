#!/usr/bin/env python3
"""Assess documented prerequisites for a personal checking opening.

Reads one JSON object from stdin and writes one JSON object to stdout.  It performs
no banking actions and has no external dependencies.
"""
import calendar
import json
import sys
from datetime import date, datetime


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing or invalid date")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError("unrecognized date format")


def subtract_months(day, months):
    month_index = day.year * 12 + (day.month - 1) - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def norm(value):
    return " ".join(str(value or "").lower().replace("_", " ").replace("-", " ").split())


def is_checking(record):
    return "checking" in norm(record.get("account_type")) or "checking" in norm(record.get("account_class"))


def is_explicit_business(record):
    fields = ("account_type", "account_class", "ownership", "account_scope", "customer_type")
    return any("business" in norm(record.get(field)) for field in fields)


def is_personal_checking(record):
    explicit = record.get("is_personal_checking")
    if isinstance(explicit, bool):
        return explicit
    # A retrieved checking account without an explicit business designation is
    # counted conservatively rather than omitted from the documented limit.
    return is_checking(record) and not is_explicit_business(record)


def is_closed(record):
    return "closed" in norm(record.get("status"))


def cause_state(record):
    """Return True, False, or None when cause cannot be determined."""
    explicit = record.get("closed_for_cause")
    if isinstance(explicit, bool):
        return explicit
    reason = norm(record.get("closure_reason") or record.get("close_reason"))
    status = norm(record.get("status"))
    combined = reason + " " + status
    if "cause" in combined and "closed" in combined:
        return True
    if reason:
        return False
    # A non-cause closure status can be affirmatively treated as not-for-cause.
    if is_closed(record) and any(word in status for word in ("customer request", "voluntary", "normal")):
        return False
    return None


def closure_date(record):
    for key in ("date_closed", "closed_at", "closure_date"):
        if record.get(key):
            return parse_date(record[key])
    return None


def main(payload):
    reasons = []
    review_required = False
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    policy = payload.get("policy")
    if not isinstance(policy, dict):
        raise ValueError("policy object is required")
    try:
        minimum_age = int(policy["minimum_age"])
        account_limit = int(policy["max_personal_checking_accounts"])
        lookback = int(policy["closure_lookback_months"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("policy must provide integer minimum_age, max_personal_checking_accounts, and closure_lookback_months") from exc

    as_of = parse_date(payload.get("as_of"))
    cutoff = subtract_months(as_of, lookback)
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile object is required")
    dob = parse_date(profile.get("date_of_birth"))
    age = as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))

    if payload.get("identity_verified") is not True:
        reasons.append("identity_not_verified")
    if age < minimum_age:
        reasons.append("below_minimum_age")

    selection = payload.get("selection")
    official = payload.get("official_account_classes")
    if not isinstance(selection, str) or not selection.strip():
        reasons.append("account_class_not_confirmed")
    elif not isinstance(official, list) or selection not in official:
        reasons.append("account_class_not_official")
    elif not selection.rstrip().endswith("Account"):
        reasons.append("account_class_does_not_use_required_official_form")

    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise ValueError("accounts must be an array from the account retrieval result")
    if any(not isinstance(record, dict) for record in accounts):
        raise ValueError("each account must be an object")

    personal_count = sum(1 for record in accounts if is_personal_checking(record))
    if personal_count > account_limit:
        reasons.append("personal_checking_account_limit_exceeded")

    for record in accounts:
        if not is_personal_checking(record) or not is_closed(record):
            continue
        cause = cause_state(record)
        if cause is None:
            review_required = True
            reasons.append("closed_checking_cause_unknown")
            continue
        if cause is False:
            continue
        try:
            closed = closure_date(record)
        except ValueError:
            closed = None
        if closed is None:
            review_required = True
            reasons.append("closed_for_cause_date_unknown")
        elif cutoff <= closed <= as_of:
            reasons.append("checking_closed_for_cause_within_lookback")

    # Preserve a stable, concise result even if several records have the same issue.
    reasons = list(dict.fromkeys(reasons))
    return {
        "eligible": not reasons and not review_required,
        "age": age,
        "personal_checking_count": personal_count,
        "reasons": reasons,
        "review_required": review_required,
        "cutoff_date": cutoff.isoformat(),
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"eligible": False, "error": str(exc)}, sort_keys=True))
