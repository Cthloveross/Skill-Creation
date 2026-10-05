#!/usr/bin/env python3
"""Read-only business checking referral eligibility and ranking helper.

Input: JSON documented in SKILL.md on stdin.
Output: JSON with gating, rolling-window, ranking, and unresolved blockers.
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
    "identity_verified", "authority_confirmed", "account_ownership_confirmed",
    "account_good_standing_confirmed",
)
PROSPECT_FLAGS = (
    "identity_available", "new_customer_confirmed",
    "different_registered_address_confirmed",
    "business_primary_owner_different_confirmed",
    "primary_authorized_signer_confirmed", "new_money_confirmed",
    "no_other_new_account_promotion_confirmed", "one_referral_code_confirmed",
)


def parse_time(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + " must be a nonempty ISO-8601 timestamp")
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(label + " is not a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(label + " must include a UTC offset or Z")
    return parsed


def missing_flags(mapping, names, prefix):
    return [prefix + name for name in names if mapping.get(name) is not True]


def main(payload):
    now = parse_time(payload.get("now"), "now")
    referrer = payload.get("referrer")
    prospect = payload.get("prospect", {})
    if not isinstance(referrer, dict):
        raise ValueError("referrer must be an object")
    if not isinstance(prospect, dict):
        raise ValueError("prospect must be an object")

    deposit = payload.get("planned_new_money_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        raise ValueError("planned_new_money_deposit must be a nonnegative number")

    referrer_blockers = missing_flags(referrer, REFERRER_FLAGS, "referrer.")
    opened_at = None
    raw_opened = referrer.get("earliest_checking_opened_at")
    if raw_opened is None:
        referrer_blockers.append("referrer.earliest_checking_opened_at")
    else:
        opened_at = parse_time(raw_opened, "referrer.earliest_checking_opened_at")
        if opened_at > now:
            referrer_blockers.append("referrer.earliest_checking_opened_at_cannot_be_in_the_future")

    raw_timestamps = referrer.get("successful_bonus_timestamps")
    timestamps = []
    if not isinstance(raw_timestamps, list):
        referrer_blockers.append("referrer.successful_bonus_timestamps")
    else:
        for index, raw in enumerate(raw_timestamps):
            stamp = parse_time(raw, "successful_bonus_timestamps[%d]" % index)
            if stamp > now:
                referrer_blockers.append("referrer.successful_bonus_timestamps_contains_future_time")
            else:
                timestamps.append(stamp)

    annual_count = referrer.get("annual_successful_bonus_count")
    if not isinstance(annual_count, int) or isinstance(annual_count, bool) or annual_count < 0:
        referrer_blockers.append("referrer.annual_successful_bonus_count")
        annual_count = None

    window_start = now - timedelta(days=9)
    in_window = [stamp for stamp in timestamps if window_start <= stamp <= now]
    rolling_blocked = len(in_window) >= 2
    if rolling_blocked:
        referrer_blockers.append("referrer.rolling_nine_day_cap_reached")

    referrer_gate_passed = not referrer_blockers
    prospect_blockers = missing_flags(prospect, PROSPECT_FLAGS, "prospect.")
    tenure_days = None
    if opened_at is not None and opened_at <= now:
        tenure_days = (now - opened_at).total_seconds() / 86400.0

    ranked = []
    excluded = []
    if referrer_gate_passed:
        for program in PROGRAMS:
            reasons = []
            if deposit < program["deposit_required"]:
                reasons.append("planned deposit is below qualifying-deposit requirement")
            if tenure_days is None or tenure_days < program["tenure_days"]:
                reasons.append("earliest-checking tenure is below requirement")
            if annual_count is None or annual_count >= program["annual_cap"]:
                reasons.append("annual referral-bonus cap reached or unconfirmed")
            if reasons:
                excluded.append({"account": program["account"], "reasons": reasons})
            else:
                ranked.append(dict(program))
        ranked.sort(key=lambda item: (-item["referrer_bonus"], item["account"]))

    return {
        "referrer_gate_passed": referrer_gate_passed,
        "referrer_blockers": referrer_blockers,
        "rolling_window": {
            "window_start": window_start.isoformat(),
            "window_end": now.isoformat(),
            "successful_bonus_count": len(in_window),
            "cap": 2,
            "blocked": rolling_blocked,
        },
        "tenure_days": None if tenure_days is None else round(tenure_days, 4),
        "ranked_programs": ranked,
        "best_program": ranked[0] if ranked else None,
        "excluded_programs": excluded,
        "submission_blockers": prospect_blockers,
        "submission_ready": referrer_gate_passed and not prospect_blockers and bool(ranked),
        "same_product_rule": (
            "The referrer's current checking product does not restrict the target product; "
            "eligibility uses tenure since the earliest checking account."
            if referrer_gate_passed else None
        ),
        "qualification_reminder": (
            "A ranked program is not a guaranteed bonus. The referred business must open the "
            "selected product, make the required external new-money deposit within its window, "
            "retain it for at least 30 days after the qualification period, and both accounts "
            "must remain in good standing."
        ),
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
