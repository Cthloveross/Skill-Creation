#!/usr/bin/env python3
"""Pure JSON referral-capacity calculator; reads stdin and writes stdout."""
import json
import sys
from datetime import datetime, date, timedelta, timezone


def parse_dt(value):
    if not isinstance(value, str) or not value:
        return None, False
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), datetime.min.time(), tzinfo=timezone.utc), True
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), False
    except ValueError:
        return None, False


def program_for(account_type):
    text = str(account_type or "").lower()
    if "gold" in text and "year" in text:
        return "gold_years"
    if "sky" in text and "blue" in text:
        return "sky_blue"
    return None


def tri(value, condition):
    if value is None:
        return "unknown"
    return "pass" if condition(value) else "fail"


def main(payload):
    now, now_date_only = parse_dt(payload.get("as_of"))
    if now is None:
        raise ValueError("as_of must be an ISO date or timestamp")
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        raise ValueError("referrals must be a list")

    complete = []
    malformed = []
    for item in referrals:
        if not isinstance(item, dict) or str(item.get("referral_status", "")).upper() != "COMPLETE":
            continue
        when, date_only = parse_dt(item.get("date"))
        if when is None:
            malformed.append(item.get("date"))
            continue
        complete.append((item, when, date_only))

    cutoff = now - timedelta(days=9)
    in_window = []
    boundary_ambiguous = []
    for item, when, date_only in complete:
        if when > cutoff:
            in_window.append(item)
        elif when == cutoff:
            if date_only:
                boundary_ambiguous.append(item)
            else:
                in_window.append(item)
        elif date_only and when.date() == cutoff.date():
            boundary_ambiguous.append(item)

    annual = {"gold_years": 0, "sky_blue": 0}
    for item, when, _ in complete:
        program = program_for(item.get("referred_account_type"))
        if program and when.year == now.year:
            annual[program] += 1

    opened, _ = parse_dt((payload.get("referrer") or {}).get("first_checking_opened"))
    tenure = {}
    for program, days in (("gold_years", 30), ("sky_blue", 45)):
        if opened is None:
            tenure[program] = {"required_days": days, "status": "unknown"}
        else:
            age_days = (now - opened).total_seconds() / 86400
            tenure[program] = {"required_days": days, "elapsed_days": int(age_days), "status": "pass" if age_days >= days else "fail"}

    reviewed = []
    for candidate in payload.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        program = candidate.get("program")
        prereqs = {
            "new_to_rho": tri(candidate.get("new_to_rho"), lambda x: x is True),
            "different_registered_address": tri(candidate.get("same_registered_address"), lambda x: x is False),
        }
        if program != "sky_blue":
            prereqs["minimum_age_18"] = tri(candidate.get("age"), lambda x: isinstance(x, (int, float)) and x >= 18)
        if program == "gold_years":
            prereqs["gold_years_age_62"] = tri(candidate.get("age"), lambda x: isinstance(x, (int, float)) and x >= 62)
            prereqs["referrer_tenure"] = tenure["gold_years"]["status"]
        elif program == "sky_blue":
            prereqs["business_within_four_years"] = tri(candidate.get("business_age_years"), lambda x: isinstance(x, (int, float)) and x <= 4)
            prereqs["distinct_business_primary_owner"] = tri(candidate.get("distinct_business_primary_owner"), lambda x: x is True)
            prereqs["referrer_tenure"] = tenure["sky_blue"]["status"]
        reviewed.append({"label": candidate.get("label", "unnamed candidate"), "program": program, "prerequisites": prereqs})

    definite_count = len(in_window)
    output = {
        "as_of": payload["as_of"],
        "rolling_nine_day": {
            "cap": 2,
            "definite_complete_bonus_count": definite_count,
            "definite_remaining_capacity": max(0, 2 - definite_count),
            "date_only_boundary_records": len(boundary_ambiguous),
            "status": "ambiguous" if boundary_ambiguous else ("at_cap" if definite_count >= 2 else "capacity_available"),
            "note": "Boundary records need exact timestamps; capacity is not approval of a referral."
        },
        "annual": {
            "calendar_year": now.year,
            "gold_years": {"cap": 6, "complete_count": annual["gold_years"], "remaining": max(0, 6 - annual["gold_years"])},
            "sky_blue": {"cap": 8, "complete_count": annual["sky_blue"], "remaining": max(0, 8 - annual["sky_blue"])}
        },
        "referrer_tenure": tenure,
        "candidates": reviewed,
        "ignored_malformed_complete_dates": malformed
    }
    return output


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
