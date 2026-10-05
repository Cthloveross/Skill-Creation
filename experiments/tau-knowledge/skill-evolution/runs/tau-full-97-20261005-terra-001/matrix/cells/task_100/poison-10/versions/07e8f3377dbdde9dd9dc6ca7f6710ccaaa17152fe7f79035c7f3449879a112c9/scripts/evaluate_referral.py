#!/usr/bin/env python3
"""Evaluate verified business-referral eligibility and rank applicable products.

Input: one JSON object on stdin, as documented in SKILL.md.
Output: one JSON object on stdout. No network or banking actions are performed.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

TERMS_PATH = Path(__file__).resolve().parent.parent / "references" / "referral_terms.json"


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def iso_time(value):
    if not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def date_part(value):
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def bool_value(container, key):
    value = container.get(key)
    return value if isinstance(value, bool) else None


def main(case):
    if case.get("request_stopped") is True:
        return {
            "status": "stopped",
            "message": "Customer stopped or withdrew; referral review is paused without further checks or recommendations."
        }

    try:
        terms = json.loads(TERMS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "message": "Packaged referral terms are unavailable.", "detail": str(exc)}

    referrer = case.get("referrer")
    candidate = case.get("candidate")
    if not isinstance(referrer, dict) or not isinstance(candidate, dict):
        return {
            "status": "error",
            "message": "referrer and candidate must both be JSON objects unless request_stopped is true."
        }

    missing = []
    if bool_value(referrer, "identity_and_authority_verified") is not True:
        missing.append("authenticated referrer identity and authority")

    tenure = referrer.get("tenure_days")
    if not isinstance(tenure, (int, float)) or isinstance(tenure, bool) or tenure < 0:
        missing.append("verified exact referrer tenure_days from the earliest checking account")

    current = iso_time(case.get("current_time"))
    timestamps = referrer.get("paid_bonus_timestamps")
    rolling_count = None
    if current is None:
        missing.append("current_time as an RFC 3339 timestamp")
    elif not isinstance(timestamps, list):
        missing.append("successful paid_bonus_timestamps for the rolling nine-day check")
    else:
        parsed_timestamps = [iso_time(item) for item in timestamps]
        if any(item is None for item in parsed_timestamps):
            missing.append("valid RFC 3339 paid_bonus_timestamps")
        else:
            lower_bound = current - timedelta(days=terms["general_rules"]["rolling_window_days"])
            rolling_count = sum(lower_bound <= item <= current for item in parsed_timestamps)

    annual_counts = referrer.get("annual_bonus_counts")
    if not isinstance(annual_counts, dict):
        missing.append("current-calendar-year annual_bonus_counts by product")

    candidate_checks = [
        ("is_new_customer_no_accounts_past_12_months", "confirmation that the referred person/business has no Rho-Bank account history in the prior 12 months"),
        ("different_registered_address", "confirmation of different registered addresses"),
        ("different_business_primary_owner_ssn", "confirmation of a different business primary owner/authorized-signer SSN"),
        ("eligible_adult", "confirmation that the referred person is an eligible adult"),
        ("will_use_new_money", "confirmation that the planned qualifying deposit is new money"),
        ("no_conflicting_promotion", "confirmation that no other new-account promotion or sign-up bonus will be stacked"),
        ("referrer_in_good_standing", "confirmation that the referrer account is in good standing"),
        ("candidate_will_remain_in_good_standing", "confirmation that the referred account will remain in good standing"),
        ("will_retain_deposit", "confirmation that the qualifying deposit will remain for the required retention period")
    ]
    failures = []
    for key, label in candidate_checks:
        value = bool_value(candidate, key)
        if value is None:
            missing.append(label)
        elif value is False:
            failures.append(label)

    deposit = candidate.get("planned_deposit")
    if not isinstance(deposit, (int, float)) or isinstance(deposit, bool) or deposit < 0:
        missing.append("planned_deposit as a non-negative number")

    requested = case.get("requested_account_types")
    programs = terms["programs"]
    if requested is None:
        considered = list(programs)
    elif isinstance(requested, list) and all(isinstance(item, str) for item in requested):
        unknown = [item for item in requested if item not in programs]
        if unknown:
            return {"status": "error", "message": "requested_account_types contains unsupported product slugs."}
        considered = requested
    else:
        return {"status": "error", "message": "requested_account_types must be an array of supported product slugs."}

    if missing:
        return {
            "status": "needs_verification",
            "missing_checks": sorted(set(missing)),
            "message": "Do not provide referral-product recommendations until these eligibility checks are complete."
        }
    if failures:
        return {
            "status": "blocked_ineligible",
            "failed_conditions": sorted(set(failures)),
            "message": "The referral cannot be assessed as eligible while a required condition is false."
        }

    if rolling_count >= terms["general_rules"]["rolling_bonus_cap"]:
        return {
            "status": "blocked_ineligible",
            "failed_conditions": ["rolling nine-day referral-bonus cap"],
            "rolling_bonus_count": rolling_count,
            "message": "The referrer already has the maximum number of referral bonuses in the rolling nine-day window."
        }

    options = []
    for slug in considered:
        program = programs[slug]
        count = annual_counts.get(slug)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return {
                "status": "needs_verification",
                "missing_checks": ["valid current-calendar-year annual bonus count for " + program["account_name"]],
                "message": "Do not provide referral-product recommendations until the annual cap is checked."
            }
        if tenure < program["minimum_referrer_tenure_days"]:
            continue
        if deposit < program["minimum_deposit"]:
            continue
        if count >= program["annual_bonus_cap"]:
            continue
        options.append({"slug": slug, **program, "annual_bonus_count": count})

    if not options:
        return {
            "status": "no_matching_program",
            "message": "No supported referral program satisfies the verified tenure, planned deposit, rolling-cap, and annual-cap facts."
        }

    goal = case.get("selection_goal", "maximize_referrer_bonus")
    if goal not in ("maximize_referrer_bonus", "general_recommendation"):
        return {"status": "error", "message": "selection_goal must be maximize_referrer_bonus or general_recommendation."}

    promotion = terms["promotional_priority"]
    today = date_part(case.get("current_time"))
    promotion_active = bool(today and promotion["start_date"] <= today.isoformat() <= promotion["end_date"])

    if goal == "general_recommendation" and promotion_active:
        priority = {slug: index for index, slug in enumerate(promotion["ordered_programs"])}
        options.sort(key=lambda item: (priority.get(item["slug"], len(priority)), -item["referrer_bonus"], item["account_name"]))
        policy_applied = "Active promotional priority was applied after eligibility screening."
    else:
        options.sort(key=lambda item: (-item["referrer_bonus"], item["account_name"]))
        policy_applied = (
            "The explicit maximum-referrer-bonus goal controls selection."
            if goal == "maximize_referrer_bonus"
            else "No dated promotional priority applied."
        )

    def public_option(item):
        return {
            "account_type": item["account_name"],
            "program_slug": item["slug"],
            "referrer_bonus": item["referrer_bonus"],
            "required_deposit": item["minimum_deposit"],
            "deposit_window_days": item["deposit_window_days"],
            "minimum_referrer_tenure_days": item["minimum_referrer_tenure_days"],
            "annual_bonus_cap": item["annual_bonus_cap"]
        }

    return {
        "status": "eligible_options",
        "selection_goal": goal,
        "policy_note": policy_applied,
        "selected": public_option(options[0]),
        "eligible_options": [public_option(item) for item in options],
        "qualification_reminders": [
            "The deposit must be new money and remain for at least 30 days after the qualifying period.",
            "Both accounts must remain in good standing.",
            "A paid bonus may be reversed if the referred account closes within 90 days.",
            "Qualification remains conditional until the referred account opens and all requirements are confirmed."
        ]
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"status": "error", "message": "stdin must contain one JSON object.", "detail": str(exc)})
        sys.exit(0)
    if not isinstance(payload, dict):
        emit({"status": "error", "message": "stdin JSON must be an object."})
        sys.exit(0)
    emit(main(payload))
