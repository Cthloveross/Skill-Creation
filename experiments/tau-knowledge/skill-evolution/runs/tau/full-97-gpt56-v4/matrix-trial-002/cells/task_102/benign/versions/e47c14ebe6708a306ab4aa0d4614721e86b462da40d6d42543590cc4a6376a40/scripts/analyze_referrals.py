#!/usr/bin/env python3
"""Summarize completed referral counts and a rolling nine-day bonus window.

Reads one JSON object from stdin; writes one JSON object to stdout. This helper
performs no banking action and does not make an eligibility decision.
"""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone


def parse_time(value):
    """Return (datetime, is_date_only), rejecting ambiguous/unzoned timestamps."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty ISO-8601 string")
    raw = value.strip()
    date_only = "T" not in raw and " " not in raw
    if date_only:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc), True
    normalized = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone offset")
    return parsed, False


def main(payload):
    now, now_date_only = parse_time(payload.get("now"))
    if now_date_only:
        raise ValueError("now must include a timezone-aware timestamp")
    referrals = payload.get("referrals", [])
    caps = payload.get("annual_caps", {})
    if not isinstance(referrals, list):
        raise ValueError("referrals must be a list")
    if not isinstance(caps, dict):
        raise ValueError("annual_caps must be an object")

    yearly = Counter()
    rolling = []
    warnings = []
    cutoff = now - timedelta(days=9)

    for index, item in enumerate(referrals):
        if not isinstance(item, dict):
            raise ValueError("each referral must be an object")
        status = str(item.get("referral_status", "")).strip().upper()
        if status != "COMPLETE":
            continue
        account_type = str(item.get("referred_account_type", "")).strip()
        if not account_type:
            raise ValueError("COMPLETE referral is missing referred_account_type")
        when, date_only = parse_time(item.get("date"))
        yearly[(when.year, account_type)] += 1
        if cutoff <= when <= now:
            rolling.append({"index": index, "account_type": account_type, "date": item["date"]})
        if date_only and abs((when - cutoff).total_seconds()) < 86400:
            warnings.append(
                "A date-only completed referral is within one day of the nine-day cutoff; exact bonus timestamp is required."
            )

    annual_counts = {}
    annual_remaining = {}
    for (year, account_type), count in sorted(yearly.items()):
        annual_counts.setdefault(str(year), {})[account_type] = count
    for account_type, cap in caps.items():
        if not isinstance(cap, int) or cap < 0:
            raise ValueError("each annual cap must be a nonnegative integer")
        count = yearly[(now.year, str(account_type).strip())]
        annual_remaining[str(account_type).strip()] = max(0, cap - count)

    if len(rolling) >= 2:
        rolling_state = "at_cap"
    else:
        rolling_state = "capacity_available"
    return {
        "completed_counts_by_year_and_account_type": annual_counts,
        "annual_remaining_for_current_year": annual_remaining,
        "rolling_nine_day_complete_bonus_count": len(rolling),
        "rolling_nine_day_complete_referrals": rolling,
        "rolling_nine_day_state": rolling_state,
        "warnings": sorted(set(warnings)),
        "method_note": "Only COMPLETE referrals were counted. The rolling result is across all account types and must use exact bonus timestamps when boundary precision matters."
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
