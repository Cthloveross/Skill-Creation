#!/usr/bin/env python3
"""Summarize normalized referral records without deciding qualification."""
import json
import sys
from datetime import datetime, timedelta, timezone

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S%z")


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_timestamp(value):
    parsed = parse_date(value)
    if parsed is None or parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def main(payload):
    warnings = []
    referrals = payload.get("referrals", [])
    if not isinstance(referrals, list):
        return {"error": "referrals must be a list"}

    dated = []
    for index, referral in enumerate(referrals):
        if not isinstance(referral, dict):
            warnings.append("Ignored a referral that was not an object.")
            continue
        parsed = parse_date(referral.get("date"))
        if parsed is None:
            warnings.append("Ignored a referral with an unparseable date.")
            continue
        dated.append((parsed, index, referral))
    latest = max(dated, key=lambda item: (item[0], item[1]))[2] if dated else None
    if latest is None:
        warnings.append("No reliably dated referral was available to select as latest.")

    as_of = parse_timestamp(payload.get("as_of"))
    raw_events = payload.get("successful_bonus_timestamps", [])
    if not isinstance(raw_events, list):
        return {"error": "successful_bonus_timestamps must be a list"}
    parsed_events = []
    for value in raw_events:
        event = parse_timestamp(value)
        if event is None:
            warnings.append("A successful-bonus timestamp lacked timezone-aware timestamp precision.")
        else:
            parsed_events.append(event)

    assessable = as_of is not None and len(parsed_events) == len(raw_events)
    count = None
    if assessable:
        start = as_of - timedelta(days=7)
        count = sum(start <= event <= as_of for event in parsed_events)
    else:
        warnings.append("Rolling seven-day limit cannot be determined without an as_of timestamp and timezone-aware successful-bonus timestamps.")

    return {
        "latest_referral": latest,
        "successful_bonus_count_in_previous_7_days": count,
        "rolling_limit_assessable": assessable,
        "warnings": warnings,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
