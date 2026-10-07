#!/usr/bin/env python3
"""Summarize referral statuses and conservatively flag likely weekly-cap denials.

Input JSON:
  {"referrals": [{"referral_status": "COMPLETE", "date": "10/20/2025",
                  "referral_id": "optional", "referred_account_type": "optional"}]}
Output JSON contains normalized records, status_counts, and cap_indicators.
"""

import json
import sys
from datetime import datetime, timezone

SUCCESS_STATUSES = {"COMPLETE", "COMPLETED", "SUCCESS", "SUCCESSFUL"}
REJECTED_STATUSES = {"REJECTED", "DENIED"}
DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S")


def parse_date(value):
    """Return a datetime for common record dates, or None if unavailable."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def public_record(record, index):
    status = str(record.get("referral_status", "UNKNOWN")).strip().upper() or "UNKNOWN"
    raw_date = record.get("date")
    parsed = parse_date(raw_date)
    result = {
        "index": index,
        "status": status,
        "date": raw_date,
        "parsed_date": parsed.isoformat(sep=" ") if parsed else None,
    }
    if record.get("referred_account_type") is not None:
        result["card_name"] = record["referred_account_type"]
    if record.get("referral_id") is not None:
        result["referral_id"] = record["referral_id"]
    return result, parsed


def analyze(referrals):
    normalized = []
    dated = []
    counts = {}
    for index, record in enumerate(referrals):
        if not isinstance(record, dict):
            raise ValueError("Every referrals entry must be an object")
        item, parsed = public_record(record, index)
        normalized.append(item)
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        if parsed is not None:
            dated.append((parsed, item))

    dated.sort(key=lambda pair: pair[0])
    completed = [(when, item) for when, item in dated if item["status"] in SUCCESS_STATUSES]
    indicators = []
    for rejected_at, rejected in dated:
        if rejected["status"] not in REJECTED_STATUSES:
            continue
        # With date-only data, only flag successes clearly earlier and less than 7 days away.
        # This avoids treating a seven-day boundary as conclusive without timestamps.
        prior = [item for when, item in completed if 0 <= (rejected_at - when).total_seconds() < 7 * 86400]
        if len(prior) >= 2:
            indicators.append({
                "rejected_referral_index": rejected["index"],
                "rejected_date": rejected["date"],
                "prior_completed_dates": [item["date"] for item in prior[-2:]],
                "assessment": "consistent_with_rolling_seven_day_cap",
                "caveat": "Record dates support the timing, but exact successful-bonus timestamps control the rolling window.",
            })

    return {
        "status_counts": counts,
        "records": normalized,
        "cap_indicators": indicators,
        "limitations": [
            "A status record alone may not include the reason for rejection.",
            "Date-only records cannot resolve exact timing at a seven-day boundary.",
        ],
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("referrals"), list):
            raise ValueError("Input must be an object containing a referrals array")
        print(json.dumps(analyze(payload["referrals"]), ensure_ascii=False, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
