#!/usr/bin/env python3
"""Summarize completed referral counts and a rolling nine-day bonus window.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes
no banking action or eligibility decision. Dates returned by normal referral
lookups may be ISO-8601 or U.S. month/day/year dates; both are supported.
"""

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

_US_DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
_TZ_NAMES = {"EST": "-05:00", "EDT": "-04:00"}


def parse_time(value):
    """Return (datetime, is_date_only), rejecting unzoned datetime values."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("date must be a nonempty date or timestamp string")
    raw = value.strip()
    if _US_DATE.fullmatch(raw):
        return datetime.strptime(raw, "%m/%d/%Y").replace(tzinfo=timezone.utc), True
    if "T" not in raw and " " not in raw:
        try:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc), True
        except ValueError as exc:
            raise ValueError("date must be ISO-8601 or M/D/YYYY") from exc

    # Support the normal time tool's "YYYY-MM-DD HH:MM:SS EST/EDT" output.
    parts = raw.rsplit(" ", 1)
    if len(parts) == 2 and parts[1] in _TZ_NAMES:
        raw = parts[0] + _TZ_NAMES[parts[1]]
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        try:
            parsed = datetime.strptime(raw, "%m/%d/%Y %H:%M:%S%z")
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601, M/D/YYYY with offset, or use EST/EDT") from exc
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
    ambiguous_boundary = []
    warnings = []
    cutoff = now - timedelta(days=9)

    for index, item in enumerate(referrals):
        if not isinstance(item, dict):
            raise ValueError("each referral must be an object")
        if str(item.get("referral_status", "")).strip().upper() != "COMPLETE":
            continue
        account_type = str(item.get("referred_account_type", "")).strip()
        if not account_type:
            raise ValueError("COMPLETE referral is missing referred_account_type")
        when, date_only = parse_time(item.get("date"))
        yearly[(when.year, account_type)] += 1
        record = {"index": index, "account_type": account_type, "date": item["date"]}
        # A date-only record on the lower-cutoff calendar date might fall on
        # either side of the exact nine-day cutoff. Do not count it as certain.
        if date_only and when.date() == cutoff.date():
            ambiguous_boundary.append(record)
            warnings.append(
                "A date-only completed referral falls on the nine-day cutoff date; exact bonus timestamp is required."
            )
        elif cutoff <= when <= now:
            rolling.append(record)

    annual_counts = {}
    annual_remaining = {}
    for (year, account_type), count in sorted(yearly.items()):
        annual_counts.setdefault(str(year), {})[account_type] = count
    for account_type, cap in caps.items():
        if not isinstance(cap, int) or isinstance(cap, bool) or cap < 0:
            raise ValueError("each annual cap must be a nonnegative integer")
        normalized = str(account_type).strip()
        if not normalized:
            raise ValueError("annual cap account type must not be empty")
        annual_remaining[normalized] = max(0, cap - yearly[(now.year, normalized)])

    if len(rolling) >= 2:
        rolling_state = "at_cap"
    elif len(rolling) + len(ambiguous_boundary) >= 2:
        rolling_state = "indeterminate_requires_exact_timestamp"
    else:
        rolling_state = "capacity_available"

    return {
        "completed_counts_by_year_and_account_type": annual_counts,
        "annual_remaining_for_current_year": annual_remaining,
        "rolling_nine_day_complete_bonus_count": len(rolling),
        "rolling_nine_day_complete_referrals": rolling,
        "rolling_nine_day_boundary_date_referrals": ambiguous_boundary,
        "rolling_nine_day_state": rolling_state,
        "warnings": sorted(set(warnings)),
        "method_note": "Only COMPLETE referrals were counted. The rolling result is across all account types; boundary-date records need exact timestamps."
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
