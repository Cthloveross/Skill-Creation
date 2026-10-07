#!/usr/bin/env python3
"""Pure JSON referral-capacity calculator; reads JSON stdin and writes JSON stdout.
It does not look up data, verify identity, or submit referrals.
"""
import json
import sys
from datetime import datetime, date, timedelta, timezone

PROGRAMS = {
    "gold_years": {"annual_cap": 6, "tenure_days": 30},
    "sky_blue": {"annual_cap": 8, "tenure_days": 45},
}


def parse_dt(value):
    """Return (UTC datetime, was_date_only), or (None, False) for invalid input."""
    if not isinstance(value, str) or not value.strip():
        return None, False
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc), True
        # Accept the declared current-time tool's common text rendering as well
        # as ISO 8601. EST/EDT are fixed offsets here; callers should prefer ISO
        # when a timezone transition could matter.
        for suffix, offset in ((" EST", -5), (" EDT", -4)):
            if text.endswith(suffix):
                parsed = datetime.strptime(text[:-4], "%Y-%m-%d %H:%M:%S")
                return parsed.replace(tzinfo=timezone(timedelta(hours=offset))).astimezone(timezone.utc), False
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), False
    except ValueError:
        return None, False


def program_for(account_type):
    text = str(account_type or "").casefold()
    if "gold" in text and "year" in text:
        return "gold_years"
    if "sky" in text and "blue" in text:
        return "sky_blue"
    return None


def tri(value, predicate):
    """Return a three-state result. Only literal JSON booleans/numbers can pass."""
    if value is None:
        return "unknown"
    return "pass" if predicate(value) else "fail"


def boolean_is(value, expected):
    return isinstance(value, bool) and value is expected


def age_at_least(value, minimum):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= minimum


def business_age_within_four(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and 0 <= value <= 4)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    now, _ = parse_dt(payload.get("as_of"))
    if now is None:
        raise ValueError("as_of must be an ISO date or timestamp")
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        raise ValueError("referrals must be a list")
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    complete, malformed = [], []
    for item in referrals:
        if not isinstance(item, dict) or str(item.get("referral_status", "")).upper() != "COMPLETE":
            continue
        when, date_only = parse_dt(item.get("date"))
        if when is None:
            malformed.append(item.get("date"))
        else:
            complete.append((item, when, date_only))

    # The nine-day boundary is inclusive for a fully timestamped referral. A
    # date-only record on the boundary cannot be classified without its time.
    cutoff = now - timedelta(days=9)
    in_window, boundary_ambiguous = [], []
    for item, when, date_only in complete:
        if when > cutoff:
            in_window.append(item)
        elif when == cutoff:
            (boundary_ambiguous if date_only else in_window).append(item)
        elif date_only and when.date() == cutoff.date():
            boundary_ambiguous.append(item)

    annual = {key: 0 for key in PROGRAMS}
    for item, when, _ in complete:
        program = program_for(item.get("referred_account_type"))
        if program and when.year == now.year:
            annual[program] += 1

    referrer = payload.get("referrer") or {}
    if not isinstance(referrer, dict):
        raise ValueError("referrer must be an object when supplied")
    opened, _ = parse_dt(referrer.get("first_checking_opened"))
    tenure = {}
    for program, terms in PROGRAMS.items():
        if opened is None:
            tenure[program] = {"required_days": terms["tenure_days"], "status": "unknown"}
        else:
            elapsed = (now - opened).total_seconds() / 86400
            tenure[program] = {
                "required_days": terms["tenure_days"],
                "elapsed_days": int(elapsed),
                "status": "pass" if elapsed >= terms["tenure_days"] else "fail",
            }

    reviewed = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        program = candidate.get("program")
        prereqs = {
            "new_to_rho": tri(candidate.get("new_to_rho"), lambda v: boolean_is(v, True)),
            "different_registered_address": tri(candidate.get("same_registered_address"), lambda v: boolean_is(v, False)),
            "no_other_new_account_promotion": tri(candidate.get("has_other_new_account_promotion"), lambda v: boolean_is(v, False)),
            "one_referral_code": tri(candidate.get("one_referral_code"), lambda v: boolean_is(v, True)),
        }
        obligations = []
        if program != "sky_blue":
            prereqs["minimum_age_18"] = tri(candidate.get("age"), lambda v: age_at_least(v, 18))
        if program == "gold_years":
            prereqs["gold_years_age_62"] = tri(candidate.get("age"), lambda v: age_at_least(v, 62))
            prereqs["referrer_tenure"] = tenure["gold_years"]["status"]
            obligations.append("$1,000 new-money deposit within 90 days of opening")
        elif program == "sky_blue":
            prereqs["business_within_four_years"] = tri(candidate.get("business_age_years"), business_age_within_four)
            prereqs["distinct_business_primary_owner"] = tri(candidate.get("distinct_business_primary_owner"), lambda v: boolean_is(v, True))
            prereqs["referrer_tenure"] = tenure["sky_blue"]["status"]
            obligations.append("$10,000 new-money deposit within 90 days of opening")
        reviewed.append({
            "label": candidate.get("label", "unnamed candidate"),
            "program": program,
            "prerequisites": prereqs,
            "future_qualification_obligations": obligations,
        })

    definite_count = len(in_window)
    rolling_status = "ambiguous" if boundary_ambiguous else ("at_cap" if definite_count >= 2 else "capacity_available")
    return {
        "as_of": payload["as_of"],
        "rolling_nine_day": {
            "cap": 2,
            "definite_complete_bonus_count": definite_count,
            "definite_remaining_capacity": max(0, 2 - definite_count),
            "date_only_boundary_records": len(boundary_ambiguous),
            "status": rolling_status,
            "note": "Capacity is not approval. Boundary records require exact timestamps.",
        },
        "annual": {
            "calendar_year": now.year,
            **{program: {"cap": terms["annual_cap"], "complete_count": annual[program],
                         "remaining": max(0, terms["annual_cap"] - annual[program])}
               for program, terms in PROGRAMS.items()},
        },
        "referrer_tenure": tenure,
        "candidates": reviewed,
        "ignored_malformed_complete_dates": malformed,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
