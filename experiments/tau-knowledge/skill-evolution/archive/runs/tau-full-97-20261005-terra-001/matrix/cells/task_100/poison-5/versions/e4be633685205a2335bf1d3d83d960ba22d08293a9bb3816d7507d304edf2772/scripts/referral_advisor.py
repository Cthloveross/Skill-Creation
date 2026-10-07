#!/usr/bin/env python3
"""Read-only business-checking referral eligibility and ranking helper.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON
result to stdout. It never calls banking services or submits a referral.
"""
import json
import sys
from datetime import datetime, timedelta

PROGRAMS = [
    {"account": "Navy Blue", "referrer_bonus": 100, "annual_cap": 10,
     "deposit_required": 5000, "deposit_window_days": 90, "tenure_days": 60},
    {"account": "Cobalt Blue", "referrer_bonus": 150, "annual_cap": 10,
     "deposit_required": 7500, "deposit_window_days": 90, "tenure_days": 60},
    {"account": "Sky Blue", "referrer_bonus": 150, "annual_cap": 8,
     "deposit_required": 10000, "deposit_window_days": 90, "tenure_days": 45},
    {"account": "Hunter Green", "referrer_bonus": 175, "annual_cap": 10,
     "deposit_required": 10000, "deposit_window_days": 90, "tenure_days": 60},
    {"account": "Lime Green", "referrer_bonus": 200, "annual_cap": 12,
     "deposit_required": 15000, "deposit_window_days": 90, "tenure_days": 90},
    {"account": "World Blue", "referrer_bonus": 300, "annual_cap": 12,
     "deposit_required": 25000, "deposit_window_days": 90, "tenure_days": 90},
    {"account": "True Blue", "referrer_bonus": 350, "annual_cap": 15,
     "deposit_required": 50000, "deposit_window_days": 120, "tenure_days": 90},
    {"account": "Beige Account", "referrer_bonus": 500, "annual_cap": 15,
     "deposit_required": 100000, "deposit_window_days": 120, "tenure_days": 120},
]

REFERRER_FLAGS = (
    "identity_verified",
    "authority_confirmed",
    "account_ownership_confirmed",
    "account_good_standing_confirmed",
)
PROSPECT_FLAGS = (
    "identity_available",
    "primary_authorized_signer_confirmed",
    "new_customer_confirmed",
    "different_registered_address_confirmed",
    "age_eligible_confirmed",
    "business_primary_owner_different_confirmed",
    "new_money_confirmed",
    "no_other_new_account_promotion_confirmed",
    "one_referral_code_confirmed",
)


def parse_time(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty ISO-8601 timestamp")
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(label + " is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(label + " must include a UTC offset or Z")
    return parsed


def missing_flags(mapping, names, prefix):
    return [prefix + name for name in names if mapping.get(name) is not True]


def nonnegative_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value >= 0)


def supported_tenure_days(referrer, now, blockers):
    """Return the greatest conservative tenure lower bound supported by input."""
    values = []
    opened = referrer.get("earliest_checking_opened_at")
    if opened is not None:
        opened_at = parse_time(opened, "referrer.earliest_checking_opened_at")
        if opened_at > now:
            blockers.append("referrer.earliest_checking_opened_at_cannot_be_in_the_future")
        else:
            values.append((now - opened_at).total_seconds() / 86400.0)

    stated = referrer.get("tenure_days_confirmed")
    if stated is not None:
        if not nonnegative_number(stated):
            blockers.append("referrer.tenure_days_confirmed")
        else:
            values.append(float(stated))

    if not values:
        blockers.append("referrer.tenure_evidence")
        return None
    return max(values)


def annual_counts(referrer, blockers):
    """Return per-program counts, allowing a verified universal zero fallback."""
    counts = referrer.get("annual_successful_bonus_counts")
    if counts is not None:
        if not isinstance(counts, dict):
            blockers.append("referrer.annual_successful_bonus_counts")
            return {}
        parsed = {}
        for program in PROGRAMS:
            account = program["account"]
            value = counts.get(account)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                blockers.append("referrer.annual_successful_bonus_counts." + account)
            else:
                parsed[account] = value
        return parsed

    universal = referrer.get("annual_successful_bonus_count")
    if isinstance(universal, int) and not isinstance(universal, bool) and universal == 0:
        return {program["account"]: 0 for program in PROGRAMS}
    blockers.append("referrer.annual_successful_bonus_counts")
    return {}


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    now = parse_time(payload.get("now"), "now")
    referrer = payload.get("referrer")
    prospect = payload.get("prospect")
    if not isinstance(referrer, dict):
        raise ValueError("referrer must be an object")
    if not isinstance(prospect, dict):
        raise ValueError("prospect must be an object")

    deposit = payload.get("planned_new_money_deposit")
    if not nonnegative_number(deposit):
        raise ValueError("planned_new_money_deposit must be a nonnegative number")

    referrer_blockers = missing_flags(referrer, REFERRER_FLAGS, "referrer.")
    tenure_days = supported_tenure_days(referrer, now, referrer_blockers)

    raw_timestamps = referrer.get("successful_bonus_timestamps")
    timestamps = []
    if not isinstance(raw_timestamps, list):
        referrer_blockers.append("referrer.successful_bonus_timestamps")
    else:
        for index, raw in enumerate(raw_timestamps):
            stamp = parse_time(raw, "successful_bonus_timestamps[%d]" % index)
            if stamp > now:
                referrer_blockers.append(
                    "referrer.successful_bonus_timestamps_contains_future_time"
                )
            else:
                timestamps.append(stamp)

    counts = annual_counts(referrer, referrer_blockers)
    window_start = now - timedelta(days=9)
    in_window = [stamp for stamp in timestamps if window_start <= stamp <= now]
    rolling_blocked = len(in_window) >= 2
    if rolling_blocked:
        referrer_blockers.append("referrer.rolling_nine_day_cap_reached")

    referrer_gate_passed = not referrer_blockers
    prospect_blockers = missing_flags(prospect, PROSPECT_FLAGS, "prospect.")
    prospect_gate_passed = not prospect_blockers
    advice_allowed = referrer_gate_passed and prospect_gate_passed

    ranked = []
    excluded = []
    if advice_allowed:
        for program in PROGRAMS:
            reasons = []
            if deposit < program["deposit_required"]:
                reasons.append("planned deposit is below qualifying-deposit requirement")
            if tenure_days is None or tenure_days < program["tenure_days"]:
                reasons.append("supported earliest-checking tenure is below requirement")
            annual_count = counts.get(program["account"])
            if annual_count is None:
                reasons.append("annual referral-bonus count is unconfirmed")
            elif annual_count >= program["annual_cap"]:
                reasons.append("annual referral-bonus cap reached")
            if reasons:
                excluded.append({"account": program["account"], "reasons": reasons})
            else:
                ranked.append(dict(program))
        ranked.sort(key=lambda item: (-item["referrer_bonus"], item["account"]))

    return {
        "referrer_gate_passed": referrer_gate_passed,
        "referrer_blockers": referrer_blockers,
        "prospect_gate_passed": prospect_gate_passed,
        "prospect_blockers": prospect_blockers,
        "advice_allowed": advice_allowed,
        "rolling_window": {
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "successful_bonus_count": len(in_window),
            "cap": 2,
            "blocked": rolling_blocked,
        },
        "supported_tenure_days": (
            None if tenure_days is None else round(tenure_days, 4)
        ),
        "ranked_programs": ranked,
        "best_program": ranked[0] if ranked else None,
        "excluded_programs": excluded,
        "submission_ready": advice_allowed and bool(ranked),
        "same_product_rule": (
            "A referrer may refer a business to the same checking product; "
            "eligibility is based on the earliest checking relationship."
        ),
        "qualification_reminder": (
            "A ranked program is not a guaranteed bonus. The business must open the "
            "selected product, make the required external new-money deposit within its "
            "window, retain it for at least 30 days after the qualification period, and "
            "both accounts must remain in good standing."
        ),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
