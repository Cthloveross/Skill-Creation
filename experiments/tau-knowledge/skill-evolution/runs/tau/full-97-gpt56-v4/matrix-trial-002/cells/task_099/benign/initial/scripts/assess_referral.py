#!/usr/bin/env python3
"""Assess documented business checking referral options.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON
assessment to stdout. This program performs no banking actions.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

PROGRAMS = (
    {"account": "Navy Blue", "bonus": 100, "deposit": 5000, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"account": "Sky Blue", "bonus": 150, "deposit": 10000, "window_days": 90, "tenure_days": 45, "annual_cap": 8},
    {"account": "Cobalt Blue", "bonus": 150, "deposit": 7500, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"account": "Hunter Green", "bonus": 175, "deposit": 10000, "window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"account": "Lime Green", "bonus": 200, "deposit": 15000, "window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"account": "World Blue", "bonus": 300, "deposit": 25000, "window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"account": "True Blue", "bonus": 350, "deposit": 50000, "window_days": 120, "tenure_days": 90, "annual_cap": 15},
    {"account": "Beige", "bonus": 500, "deposit": 100000, "window_days": 120, "tenure_days": 120, "annual_cap": 15},
)


def parse_datetime(value):
    if not value:
        return None
    value = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalized_account(value):
    value = (value or "").lower().replace("account", "").strip()
    return " ".join(value.split())


def main(data):
    as_of = parse_datetime(data.get("as_of"))
    if as_of is None:
        raise ValueError("as_of must be an ISO-8601 timestamp")
    try:
        deposit = float(data["planned_deposit"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("planned_deposit must be numeric")

    tenure = data.get("referrer_tenure_days")
    if tenure is not None:
        try:
            tenure = float(tenure)
        except (TypeError, ValueError):
            raise ValueError("referrer_tenure_days must be numeric or null")

    referrals = data.get("referrals", [])
    if not isinstance(referrals, list):
        raise ValueError("referrals must be a list")

    complete = [r for r in referrals if str(r.get("referral_status", "")).upper() == "COMPLETE"]
    cutoff = as_of - timedelta(days=9)
    recent_exact = []
    boundary_unknown = False
    for record in complete:
        stamp = parse_datetime(record.get("timestamp"))
        if stamp is not None:
            if cutoff <= stamp <= as_of:
                recent_exact.append(record)
            continue
        day = parse_datetime(record.get("date"))
        if day is None:
            boundary_unknown = True
        # A date at least ten whole calendar days before the as-of date is
        # safely outside the nine-day rolling period. Nearer date-only data
        # cannot establish the exact timestamp-based result.
        elif (as_of.date() - day.date()).days <= 9:
            boundary_unknown = True

    rolling = {
        "completed_bonuses_with_exact_timestamps_in_last_9_days": len(recent_exact),
        "date_only_boundary_unknown": boundary_unknown,
        "status": "blocked" if len(recent_exact) >= 2 else ("unknown" if boundary_unknown else "pass"),
    }

    party = data.get("referred_party", {})
    party_fields = (
        "new_customer_no_account_past_12_months",
        "different_registered_address",
        "different_business_primary_owner_ssn",
    )
    party_checks = {key: str(party.get(key, "unknown")).lower() for key in party_fields}
    invalid_party_values = [key for key, value in party_checks.items() if value not in {"true", "false", "unknown"}]
    if invalid_party_values:
        raise ValueError("referred_party values must be true, false, or unknown: " + ", ".join(invalid_party_values))

    ranked, ineligible = [], []
    for program in PROGRAMS:
        failures = []
        if deposit < program["deposit"]:
            failures.append("planned deposit of ${:,.2f} is below the ${:,.2f} qualifying deposit".format(deposit, program["deposit"]))
        if tenure is None:
            failures.append("referrer checking tenure has not been established")
        elif tenure < program["tenure_days"]:
            failures.append("referrer tenure is below the {}-day requirement".format(program["tenure_days"]))

        target = normalized_account(program["account"])
        completed_this_year = sum(
            1 for r in complete
            if normalized_account(r.get("referred_account_type")) == target
            and (parse_datetime(r.get("timestamp")) or parse_datetime(r.get("date")))
            and (parse_datetime(r.get("timestamp")) or parse_datetime(r.get("date"))).year == as_of.year
        )
        if completed_this_year >= program["annual_cap"]:
            failures.append("{} completed {} referrals already recorded this calendar year, reaching the annual cap".format(completed_this_year, program["account"]))
        if rolling["status"] == "blocked":
            failures.append("two completed bonuses are already confirmed in the rolling nine-day window")

        entry = dict(program)
        entry["completed_target_referrals_this_calendar_year"] = completed_this_year
        if failures:
            entry["reasons"] = failures
            ineligible.append(entry)
        else:
            ranked.append(entry)

    ranked.sort(key=lambda item: (-item["bonus"], item["account"]))
    recommendation = ranked[0] if ranked else None
    conditions = [key for key, value in party_checks.items() if value == "unknown"]
    failed_party = [key for key, value in party_checks.items() if value == "false"]
    if recommendation is not None:
        recommendation = dict(recommendation)
        recommendation["conditional"] = bool(conditions) or rolling["status"] == "unknown"
        recommendation["unresolved_conditions"] = conditions + (["exact rolling-window timestamps"] if rolling["status"] == "unknown" else [])

    return {
        "recommendation": recommendation,
        "ranked_eligible_programs": ranked,
        "ineligible_programs": ineligible,
        "referrer_checks": {"tenure_days": tenure, "rolling_window": rolling},
        "referred_party_checks": {"values": party_checks, "unresolved": conditions, "failed": failed_party},
        "general_conditions": [
            "Qualifying deposit must be new money and retained at least 30 days after the qualifying period.",
            "Only one referral code may be used and it cannot be combined with another new-account promotion.",
            "A bonus may be clawed back if the referred account closes within 90 days; both accounts must remain in good standing.",
        ],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
