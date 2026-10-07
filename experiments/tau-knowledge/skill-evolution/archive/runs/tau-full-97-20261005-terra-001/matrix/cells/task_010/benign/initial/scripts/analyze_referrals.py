#!/usr/bin/env python3
"""Analyze structured credit-card referral records without making any account changes.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md for
schema and interpretation limits.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta

VALID_STATUSES = {
    "COMPLETE",
    "IN_PROGRESS",
    "NO_PROGRESS",
    "APPLIED",
    "REJECTED",
    "ERROR",
}

STATUS_EXPLANATIONS = {
    "COMPLETE": "Qualifying criteria have been met; the bonus is granted under the applicable program terms.",
    "IN_PROGRESS": "The referred person opened an account and is still working toward qualifying criteria; no bonus is due yet.",
    "NO_PROGRESS": "The invited person has not applied yet.",
    "APPLIED": "The application was submitted and is awaiting a decision.",
    "REJECTED": "The referral was rejected. Review existing referral activity; do not advise an immediate retry.",
    "ERROR": "An error occurred in the referral process; retry later or use the normal internal escalation path if it persists.",
}

CARD_TERMS = {
    "Silver Rewards Card": {
        "qualifying_requirement": "Approval and at least $750 in spend within 60 days of account opening.",
        "payout_timing": "Typically one to two billing cycles after the requirement is met.",
    },
    "Platinum Rewards Card": {
        "qualifying_requirement": "Approval and at least $1,500 in spend within 90 days of account opening.",
        "payout_timing": "Credited after the applicant is approved and meets that requirement within 90 days.",
    },
}


def parse_date(value):
    """Return a date from an ISO calendar-date string; reject timestamp/locale ambiguity."""
    if not isinstance(value, str):
        raise ValueError("must be a YYYY-MM-DD string")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("must be a YYYY-MM-DD string") from exc
    return parsed


def record_label(record, index):
    value = record.get("referral_id")
    return value if isinstance(value, str) and value else "record_{}".format(index + 1)


def validate_and_normalize(payload):
    errors = []
    if not isinstance(payload, dict):
        return None, ["input must be a JSON object"]
    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        return None, ["referrals must be an array"]

    normalized = []
    for index, raw in enumerate(referrals):
        prefix = "referrals[{}]".format(index)
        if not isinstance(raw, dict):
            errors.append(prefix + " must be an object")
            continue
        status = raw.get("referral_status")
        card_name = raw.get("referred_account_type")
        if status not in VALID_STATUSES:
            errors.append(prefix + ".referral_status must be one of " + ", ".join(sorted(VALID_STATUSES)))
        if not isinstance(card_name, str) or not card_name.strip():
            errors.append(prefix + ".referred_account_type must be a nonempty string")
        try:
            day = parse_date(raw.get("date"))
        except ValueError as exc:
            errors.append(prefix + ".date " + str(exc))
            day = None
        if status in VALID_STATUSES and isinstance(card_name, str) and card_name.strip() and day:
            normalized.append({
                "referral_id": record_label(raw, index),
                "referred_account_type": card_name.strip(),
                "referral_status": status,
                "date": raw["date"],
                "parsed_date": day,
            })
    if errors:
        return None, errors
    return normalized, []


def analyze(referrals, as_of=None):
    counts = Counter(item["referral_status"] for item in referrals)
    records = []
    for item in referrals:
        status = item["referral_status"]
        output = {
            "referral_id": item["referral_id"],
            "referred_account_type": item["referred_account_type"],
            "referral_status": status,
            "date": item["date"],
            "interpretation": STATUS_EXPLANATIONS[status],
        }
        terms = CARD_TERMS.get(item["referred_account_type"])
        if terms and status in {"IN_PROGRESS", "COMPLETE"}:
            output["documented_card_terms"] = terms
        elif status == "IN_PROGRESS":
            output["documented_card_terms"] = {
                "qualifying_requirement": "Card-specific qualification criteria remain to be met; terms were not supplied for this card."
            }
        records.append(output)

    completed = [item for item in referrals if item["referral_status"] == "COMPLETE"]
    cap_reviews = []
    for rejected in (item for item in referrals if item["referral_status"] == "REJECTED"):
        window_start = rejected["parsed_date"] - timedelta(days=7)
        candidates = [
            complete for complete in completed
            if window_start <= complete["parsed_date"] <= rejected["parsed_date"]
        ]
        cap_reviews.append({
            "rejected_referral_id": rejected["referral_id"],
            "rejected_date": rejected["date"],
            "calendar_date_window_checked": {
                "start_inclusive": window_start.isoformat(),
                "end_inclusive": rejected["date"],
            },
            "complete_referrals_in_window": [
                {"referral_id": item["referral_id"], "date": item["date"]}
                for item in candidates
            ],
            "plausible_from_dates": len(candidates) >= 2,
            "interpretation": (
                "This rejection is consistent with the two-successful-referral rolling seven-day cap based on record dates. "
                "Exact timestamps are required to confirm the cap."
                if len(candidates) >= 2 else
                "The available dates do not show two completed referrals in the preceding seven calendar days. "
                "The live REJECTED status remains authoritative, and exact timestamps may be needed to assess the cap."
            ),
        })

    return {
        "ok": True,
        "as_of": as_of,
        "total_referrals": len(referrals),
        "status_counts": {status: counts.get(status, 0) for status in sorted(VALID_STATUSES)},
        "records": records,
        "cap_reviews": cap_reviews,
        "limitations": [
            "A record date is not an exact event timestamp; rolling-cap conclusions from this output are plausibility checks only.",
            "The analysis does not determine invitee spend, approval evidence beyond the recorded status, payout posting, or undocumented card terms.",
        ],
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["invalid JSON: " + str(exc)]}))
        return

    referrals, errors = validate_and_normalize(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}))
        return

    as_of = payload.get("as_of")
    if as_of is not None and not isinstance(as_of, str):
        print(json.dumps({"ok": False, "errors": ["as_of must be a string when provided"]}))
        return
    print(json.dumps(analyze(referrals, as_of), sort_keys=True))


if __name__ == "__main__":
    main()
