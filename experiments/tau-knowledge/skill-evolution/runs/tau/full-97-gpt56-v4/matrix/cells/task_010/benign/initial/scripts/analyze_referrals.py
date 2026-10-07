#!/usr/bin/env python3
"""Summarize referral statuses and date-level rolling-cap indicators.

Input JSON: {"referrals": [{"referral_status": str, "date": "YYYY-MM-DD",
"referred_account_type": str, ...}, ...]}
Output JSON contains privacy-minimized status buckets and cap_indicators.
"""
import json
import sys
from datetime import date, timedelta


def parse_day(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def public_referral(record):
    return {
        "card_type": record.get("referred_account_type"),
        "status": record.get("referral_status"),
        "date": record.get("date"),
    }


def main():
    payload = json.load(sys.stdin)
    referrals = payload.get("referrals")
    if not isinstance(referrals, list):
        raise ValueError("'referrals' must be a JSON list")

    buckets = {"complete": [], "in_progress": [], "rejected": [], "other": []}
    normalized = []
    for raw in referrals:
        if not isinstance(raw, dict):
            continue
        status = raw.get("referral_status")
        view = public_referral(raw)
        if status == "COMPLETE":
            buckets["complete"].append(view)
        elif status == "IN_PROGRESS":
            buckets["in_progress"].append(view)
        elif status == "REJECTED":
            buckets["rejected"].append(view)
        else:
            buckets["other"].append(view)
        normalized.append((raw, parse_day(raw.get("date"))))

    completed = [(raw, day) for raw, day in normalized
                 if raw.get("referral_status") == "COMPLETE" and day is not None]
    indicators = []
    for raw, rejected_day in normalized:
        if raw.get("referral_status") != "REJECTED" or rejected_day is None:
            continue
        # A completed referral on the same day or in the six prior days is within
        # the seven calendar dates ending on rejected_day. Exact timestamps, if
        # available from the source system, remain authoritative.
        prior = [day.isoformat() for _, day in completed
                 if timedelta(0) <= rejected_day - day < timedelta(days=7)]
        if len(prior) >= 2:
            indicators.append({
                "rejected": public_referral(raw),
                "earlier_complete_dates": sorted(prior),
                "interpretation": (
                    "Date-level record is consistent with the shared rolling "
                    "seven-day two-bonus cap; exact timestamps are authoritative."
                ),
            })

    output = dict(buckets)
    output["cap_indicators"] = indicators
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
